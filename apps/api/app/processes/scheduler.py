"""Small durable scheduler loop: recover expired leases and surface due work."""

import time
from collections.abc import Iterable, Mapping
from typing import Any, cast

from sqlmodel import Session, select

from app.config import get_settings
from app.control.enums import TaskKind, TaskStatus
from app.control.models import ControlTask
from app.control.repositories import (
    enqueue_task_with_status,
    recover_expired_task,
)
from app.db import get_engine
from app.models import AgentRun, RunStatus, utc_now


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
    return recover_expired_task(
        session,
        task_id=task_id,
        worker_id=worker_id,
        lease_version=lease_version,
        status=status,
        lease_expires_at=lease_expires_at,
        now=now,
    )


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
