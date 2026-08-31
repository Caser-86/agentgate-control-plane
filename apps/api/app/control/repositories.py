from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import or_, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlmodel import Session, select

from app.config import get_settings
from app.control.enums import SideEffectCertainty, TaskKind, TaskOutcome, TaskStatus
from app.control.models import ControlTask, OutboxEvent
from app.models import utc_now

MAX_RECOVERY_ATTEMPTS = 3
MAX_RECOVERY_BACKOFF_SECONDS = 30


def enqueue_task(
    session: Session, *, kind: TaskKind, payload: dict[str, object], idempotency_key: str,
    capability: str, run_id: UUID | None = None,
    side_effect_certainty: SideEffectCertainty = SideEffectCertainty.READ_ONLY,
) -> ControlTask:
    return enqueue_task_with_status(
        session,
        kind=kind,
        payload=payload,
        idempotency_key=idempotency_key,
        capability=capability,
        run_id=run_id,
        side_effect_certainty=side_effect_certainty,
    )[0]


def enqueue_task_with_status(
    session: Session, *, kind: TaskKind, payload: dict[str, object], idempotency_key: str,
    capability: str, run_id: UUID | None = None,
    side_effect_certainty: SideEffectCertainty = SideEffectCertainty.READ_ONLY,
) -> tuple[ControlTask, bool]:
    existing = session.exec(
        select(ControlTask).where(ControlTask.idempotency_key == idempotency_key)
    ).first()
    if existing is not None:
        return existing, False
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
                return created, True
        existing = session.exec(
            select(ControlTask).where(ControlTask.idempotency_key == idempotency_key)
        ).one()
        return existing, False
    task = ControlTask(
        kind=kind, payload=payload, idempotency_key=idempotency_key, capability=capability,
        run_id=run_id, side_effect_certainty=side_effect_certainty,
    )
    session.add(task)
    session.flush()
    return task, True


def _expired_lease(task: ControlTask, now: datetime) -> bool:
    if task.lease_expires_at is None:
        return False
    expiry = task.lease_expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return expiry <= now


def _recovery_backoff_seconds(attempts: int) -> int:
    return int(min(2**attempts, MAX_RECOVERY_BACKOFF_SECONDS))


def recover_expired_task(
    session: Session,
    *,
    task_id: UUID,
    worker_id: UUID | None,
    lease_version: int,
    status: TaskStatus,
    lease_expires_at: datetime,
    now: datetime,
) -> bool:
    """Atomically recover one captured expired lease and append its evidence."""
    task = session.get(ControlTask, task_id)
    if task is None:
        return False
    attempts = task.attempts + 1
    to_manual_review = (
        task.side_effect_certainty == SideEffectCertainty.POSSIBLE
        or attempts >= MAX_RECOVERY_ATTEMPTS
    )
    next_status = TaskStatus.MANUAL_REVIEW if to_manual_review else TaskStatus.QUEUED
    values: dict[str, object] = {
        "status": next_status.value,
        "lease_owner_id": None,
        "lease_expires_at": None,
        "updated_at": now,
        "attempts": attempts,
    }
    if to_manual_review:
        values["completed_at"] = now
    else:
        values["available_at"] = now + timedelta(seconds=_recovery_backoff_seconds(attempts))
    updated = session.execute(
        update(ControlTask)
        .where(
            cast(Any, ControlTask.id) == task_id,
            cast(Any, ControlTask.lease_owner_id) == worker_id,
            cast(Any, ControlTask.lease_version) == lease_version,
            cast(Any, ControlTask.status) == status,
            cast(Any, ControlTask.lease_expires_at) == lease_expires_at,
            cast(Any, ControlTask.lease_expires_at) <= now,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if cast(Any, updated).rowcount != 1:
        return False
    from app.repositories import AuditRepository
    from app.services.audit import AuditService

    AuditService(AuditRepository(session)).append(
        event_type="task.lease_recovered",
        actor="scheduler",
        payload={"status": next_status.value, "attempts": attempts},
        resource_type="control_task",
        resource_id=task_id,
        commit=False,
    )
    append_outbox_event(
        session,
        event_type="task.updated",
        resource_type="control_task",
        resource_id=task_id,
        payload={"status": next_status.value, "recovered": True},
    )
    return True


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
    lease_expires_at = task.lease_expires_at
    if _expired_lease(task, now) and task.side_effect_certainty == SideEffectCertainty.POSSIBLE:
        assert lease_expires_at is not None
        recover_expired_task(
            session, task_id=task.id, worker_id=task.lease_owner_id,
            lease_version=task.lease_version, status=task.status,
            lease_expires_at=lease_expires_at, now=now,
        )
        session.expire(task)
        return None
    if _expired_lease(task, now):
        assert lease_expires_at is not None
        recover_expired_task(
            session, task_id=task.id, worker_id=task.lease_owner_id,
            lease_version=task.lease_version, status=task.status,
            lease_expires_at=lease_expires_at, now=now,
        )
        session.expire(task)
        return None
    task.status = TaskStatus.LEASED
    task.lease_version += 1
    task.lease_owner_id = worker_id
    task.lease_expires_at = now + timedelta(seconds=get_settings().worker_lease_seconds)
    task.started_at = task.started_at or now
    task.updated_at = now
    session.flush()
    return task


def renew_task_lease(
    session: Session, *, task_id: UUID, worker_id: UUID, lease_version: int, now: datetime,
) -> bool:
    updated = session.execute(
        update(ControlTask)
        .where(
            cast(Any, ControlTask.id) == task_id,
            cast(Any, ControlTask.lease_owner_id) == worker_id,
            cast(Any, ControlTask.lease_version) == lease_version,
            cast(Any, ControlTask.status).in_([TaskStatus.LEASED, TaskStatus.RUNNING]),
            cast(Any, ControlTask.lease_expires_at) > now,
        )
        .values(
            lease_expires_at=now + timedelta(seconds=get_settings().worker_lease_seconds),
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return bool(cast(Any, updated).rowcount == 1)


def start_task(
    session: Session, *, task_id: UUID, worker_id: UUID, lease_version: int, now: datetime,
) -> bool:
    updated = session.execute(
        update(ControlTask)
        .where(
            cast(Any, ControlTask.id) == task_id,
            cast(Any, ControlTask.lease_owner_id) == worker_id,
            cast(Any, ControlTask.lease_version) == lease_version,
            cast(Any, ControlTask.status) == TaskStatus.LEASED,
            cast(Any, ControlTask.lease_expires_at) > now,
        )
        .values(status=TaskStatus.RUNNING, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    return bool(cast(Any, updated).rowcount == 1)


def complete_task(
    session: Session, *, task_id: UUID, worker_id: UUID, outcome: TaskOutcome,
    result: dict[str, object], lease_version: int,
) -> ControlTask:
    completed_at = utc_now()
    updated = session.execute(
        update(ControlTask)
        .where(
            cast(Any, ControlTask.id) == task_id,
            cast(Any, ControlTask.lease_owner_id) == worker_id,
            cast(Any, ControlTask.lease_version) == lease_version,
            cast(Any, ControlTask.status).in_([TaskStatus.LEASED, TaskStatus.RUNNING]),
            cast(Any, ControlTask.lease_expires_at) > completed_at,
        )
        .values(
            status=TaskStatus(outcome.value),
            result=result,
            completed_at=completed_at,
            updated_at=completed_at,
            lease_owner_id=None,
            lease_expires_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    if cast(Any, updated).rowcount != 1:
        raise ValueError("task lease ownership or version has changed")
    session.expire_all()
    task = session.get(ControlTask, task_id)
    if task is None:
        raise ValueError("task disappeared after completion")
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
