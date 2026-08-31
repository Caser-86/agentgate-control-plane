"""Small durable scheduler loop: recover expired leases and surface due work."""

import time
from collections.abc import Iterable, Mapping
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import update
from sqlmodel import Session, select

from app.config import get_settings
from app.control.enums import SideEffectCertainty, TaskKind, TaskStatus
from app.control.models import ControlTask
from app.control.repositories import (
    MAX_RECOVERY_ATTEMPTS,
    MAX_RECOVERY_BACKOFF_SECONDS,
    append_outbox_event,
    enqueue_task_with_status,
)
from app.db import get_engine
from app.models import AgentRun, RunStatus, utc_now
from app.repositories import AuditRepository
from app.services.audit import AuditService


def recover_expired_lease(
    session: Session,
    *,
    task_id: Any,
    worker_id: Any,
    lease_version: int,
    status: TaskStatus,
    lease_expires_at: Any,
    now: Any,
) -> bool:
    """Recover only the lease represented by the captured scheduler snapshot."""
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
        values["available_at"] = now + timedelta(
            seconds=min(2**attempts, MAX_RECOVERY_BACKOFF_SECONDS)
        )
    result = session.execute(
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
    if cast(Any, result).rowcount != 1:
        return False
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


def _enqueue_due_tasks(session: Session, due_tasks: Iterable[Mapping[str, object]]) -> int:
    enqueued = 0
    for due_task in due_tasks:
        _, created = enqueue_task_with_status(
            session,
            kind=cast(TaskKind, due_task["kind"]),
            payload=cast(dict[str, object], due_task["payload"]),
            idempotency_key=cast(str, due_task["idempotency_key"]),
            capability=cast(str, due_task["capability"]),
            run_id=cast(Any, due_task.get("run_id")),
        )
        enqueued += int(created)
    return enqueued


def enqueue_due_tasks(due_tasks: Iterable[Mapping[str, object]]) -> int:
    """Persist due task specifications through the durable idempotent queue."""
    with Session(get_engine()) as session:
        enqueued = _enqueue_due_tasks(session, due_tasks)
        session.commit()
    return enqueued


def _discover_due_tasks(session: Session) -> list[dict[str, object]]:
    runs = session.exec(
        cast(
            Any,
            select(AgentRun).where(cast(Any, AgentRun.status) == RunStatus.QUEUED),
        )
    ).all()
    return [
        {
            "kind": TaskKind.AGENT_RUN,
            "payload": {"run_id": str(run.id)},
            "idempotency_key": f"agent-run-resume:{run.id}:initial",
            "capability": "control.run",
            "run_id": run.id,
        }
        for run in runs
    ]


def run_once() -> int:
    now = utc_now()
    changed = 0
    with Session(get_engine()) as session:
        changed += _enqueue_due_tasks(session, _discover_due_tasks(session))
        tasks = session.exec(
            cast(
                Any,
                select(ControlTask).where(
                    cast(Any, ControlTask.status).in_([TaskStatus.LEASED, TaskStatus.RUNNING]),
                    cast(Any, ControlTask.lease_expires_at) <= now,
                ),
            )
        ).all()
        for task in tasks:
            changed += int(
                recover_expired_lease(
                    session,
                    task_id=task.id,
                    worker_id=task.lease_owner_id,
                    lease_version=task.lease_version,
                    status=task.status,
                    lease_expires_at=task.lease_expires_at,
                    now=now,
                )
            )
        session.commit()
    return changed


def run_forever() -> None:
    while True:
        run_once()
        time.sleep(max(1, get_settings().worker_lease_seconds // 3))


if __name__ == "__main__":
    run_forever()
