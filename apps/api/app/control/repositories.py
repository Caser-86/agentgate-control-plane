from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlmodel import Session, select

from app.config import get_settings
from app.control.enums import SideEffectCertainty, TaskKind, TaskOutcome, TaskStatus
from app.control.models import ControlTask, OutboxEvent
from app.models import utc_now


def enqueue_task(
    session: Session, *, kind: TaskKind, payload: dict[str, object], idempotency_key: str,
    capability: str, run_id: UUID | None = None,
    side_effect_certainty: SideEffectCertainty = SideEffectCertainty.READ_ONLY,
) -> ControlTask:
    existing = session.exec(
        select(ControlTask).where(ControlTask.idempotency_key == idempotency_key)
    ).first()
    if existing is not None:
        return existing
    if session.get_bind().dialect.name == "postgresql":
        task_id = uuid4()
        created_at = utc_now()
        inserted_id = session.execute(
            postgresql_insert(ControlTask)
            .values(
                id=task_id,
                kind=kind.value,
                status=TaskStatus.QUEUED.value,
                payload=payload,
                capability=capability,
                idempotency_key=idempotency_key,
                run_id=run_id,
                attempts=0,
                available_at=created_at,
                created_at=created_at,
                updated_at=created_at,
                side_effect_certainty=side_effect_certainty.value,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(cast(Any, ControlTask.id))
        ).scalar_one_or_none()
        if inserted_id is not None:
            created = session.get(ControlTask, inserted_id)
            if created is not None:
                return created
        existing = session.exec(
            select(ControlTask).where(ControlTask.idempotency_key == idempotency_key)
        ).one()
        return existing
    task = ControlTask(
        kind=kind, payload=payload, idempotency_key=idempotency_key, capability=capability,
        run_id=run_id, side_effect_certainty=side_effect_certainty,
    )
    session.add(task)
    session.flush()
    return task


def _expired_lease(task: ControlTask, now: datetime) -> bool:
    return task.lease_expires_at is not None and task.lease_expires_at <= now


def claim_next_task(
    session: Session, *, worker_id: UUID, capabilities: set[str], now: datetime,
) -> ControlTask | None:
    if not capabilities:
        return None
    statement = (
        select(ControlTask)
        .where(
            cast(Any, ControlTask.capability).in_(capabilities),
            or_(
                (cast(Any, ControlTask.status) == TaskStatus.QUEUED)
                & (cast(Any, ControlTask.available_at) <= now),
                (cast(Any, ControlTask.status).in_([TaskStatus.LEASED, TaskStatus.RUNNING]))
                & (cast(Any, ControlTask.lease_expires_at) <= now),
            ),
        )
        .order_by(cast(Any, ControlTask.available_at), cast(Any, ControlTask.created_at))
        .with_for_update(skip_locked=True)
    )
    task = session.exec(statement).first()
    if task is None:
        return None
    if _expired_lease(task, now) and task.side_effect_certainty == SideEffectCertainty.POSSIBLE:
        task.status = TaskStatus.MANUAL_REVIEW
        task.completed_at = now
        task.lease_owner_id = None
        task.lease_expires_at = None
        task.updated_at = now
        session.flush()
        return None
    if _expired_lease(task, now):
        task.attempts += 1
    task.status = TaskStatus.LEASED
    task.lease_owner_id = worker_id
    task.lease_expires_at = now + timedelta(seconds=get_settings().worker_lease_seconds)
    task.started_at = task.started_at or now
    task.updated_at = now
    session.flush()
    return task


def renew_task_lease(
    session: Session, *, task_id: UUID, worker_id: UUID, now: datetime,
) -> ControlTask:
    task = session.get(ControlTask, task_id)
    if task is None or task.lease_owner_id != worker_id or task.status not in {
        TaskStatus.LEASED, TaskStatus.RUNNING
    }:
        raise ValueError("task lease is not owned by this worker")
    task.lease_expires_at = now + timedelta(seconds=get_settings().worker_lease_seconds)
    task.updated_at = now
    session.flush()
    return task


def complete_task(
    session: Session, *, task_id: UUID, worker_id: UUID, outcome: TaskOutcome,
    result: dict[str, object],
) -> ControlTask:
    task = session.get(ControlTask, task_id)
    if task is None or task.lease_owner_id != worker_id or task.status not in {
        TaskStatus.LEASED, TaskStatus.RUNNING
    }:
        raise ValueError("task is not completable by this worker")
    task.status = TaskStatus(outcome.value)
    task.result = result
    task.completed_at = utc_now()
    task.updated_at = task.completed_at
    task.lease_owner_id = None
    task.lease_expires_at = None
    session.flush()
    return task


def append_outbox_event(
    session: Session, *, event_type: str, resource_type: str, resource_id: UUID,
    payload: dict[str, object],
) -> OutboxEvent:
    event = OutboxEvent(
        event_type=event_type, resource_type=resource_type, resource_id=resource_id, payload=payload
    )
    session.add(event)
    session.flush()
    return event


def read_outbox_after(session: Session, *, cursor: int, limit: int) -> list[OutboxEvent]:
    return list(
        session.exec(
            select(OutboxEvent)
            .where(cast(Any, OutboxEvent.sequence) > cursor)
            .order_by(cast(Any, OutboxEvent.sequence))
            .limit(limit)
        ).all()
    )
