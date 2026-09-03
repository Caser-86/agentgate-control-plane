"""Small durable scheduler loop: recover expired leases and surface due work."""

import time
from collections.abc import Iterable, Mapping
from datetime import timedelta
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
from app.monitoring.enums import TargetKind
from app.monitoring.models import MonitorTarget
from app.services.monitoring import capability_for_kind


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


def discover_due_tasks(session: Session, *, now: Any | None = None) -> list[dict[str, object]]:
    observed_at = now or utc_now()
    runs = session.exec(
        cast(
            Any,
            select(AgentRun).where(cast(Any, AgentRun.status) == RunStatus.QUEUED),
        )
    ).all()
    due_tasks: list[dict[str, object]] = [
        {
            "kind": TaskKind.AGENT_RUN,
            "payload": {"run_id": str(run.id)},
            "idempotency_key": f"agent-run-resume:{run.id}:initial",
            "capability": "control.run",
            "run_id": run.id,
        }
        for run in runs
    ]
    targets = session.exec(
        cast(
            Any,
            select(MonitorTarget).where(
                cast(Any, MonitorTarget.enabled).is_(True),
                cast(Any, MonitorTarget.next_probe_at) <= observed_at,
            ),
        )
    ).all()
    pending_tasks = session.exec(
        cast(
            Any,
            select(ControlTask).where(
                cast(Any, ControlTask.kind) == TaskKind.CONTROL,
                cast(Any, ControlTask.status).in_(
                    [TaskStatus.QUEUED, TaskStatus.LEASED, TaskStatus.RUNNING]
                ),
            ),
        )
    ).all()
    pending_target_ids = {
        str(task.payload.get("target_id"))
        for task in pending_tasks
        if isinstance(task.payload, dict)
        and str(task.payload.get("task_type", "")).startswith("monitor.")
    }
    for target in targets:
        if str(target.id) in pending_target_ids:
            continue
        try:
            target_kind = TargetKind(target.kind)
        except ValueError:
            continue
        capability = capability_for_kind(target_kind)
        due_tasks.append(
            {
                "kind": TaskKind.CONTROL,
                "payload": {
                    "task_type": capability,
                    "target_id": str(target.id),
                    "endpoint": target.endpoint,
                    "timeout_seconds": target.timeout_seconds,
                },
                "idempotency_key": f"monitor-probe:{target.id}:{int(observed_at.timestamp())}",
                "capability": capability,
            }
        )
        target.next_probe_at = observed_at + timedelta(seconds=target.interval_seconds)
        target.updated_at = observed_at
        session.add(target)
    return due_tasks


def _discover_due_tasks(session: Session) -> list[dict[str, object]]:
    """Backward-compatible scheduler helper used by existing tests."""
    return discover_due_tasks(session)


def run_once() -> int:
    now = utc_now()
    changed = 0
    with Session(get_engine()) as session:
        changed += _enqueue_due_tasks(session, discover_due_tasks(session, now=now))
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
