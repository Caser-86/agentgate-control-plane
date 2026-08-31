"""Small durable scheduler loop: recover expired leases and surface due work."""

import time
from datetime import timedelta
from typing import Any, cast

from sqlmodel import Session, select

from app.config import get_settings
from app.control.enums import SideEffectCertainty, TaskStatus
from app.control.models import ControlTask
from app.control.repositories import MAX_RECOVERY_ATTEMPTS, MAX_RECOVERY_BACKOFF_SECONDS
from app.db import get_engine
from app.models import utc_now


def run_once() -> int:
    now = utc_now()
    changed = 0
    with Session(get_engine()) as session:
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
            task.lease_owner_id = None
            task.lease_expires_at = None
            task.updated_at = now
            task.attempts += 1
            if (
                task.side_effect_certainty == SideEffectCertainty.POSSIBLE
                or task.attempts >= MAX_RECOVERY_ATTEMPTS
            ):
                task.status = TaskStatus.MANUAL_REVIEW
                task.completed_at = now
            else:
                task.status = TaskStatus.QUEUED
                task.available_at = now + timedelta(
                    seconds=min(2**task.attempts, MAX_RECOVERY_BACKOFF_SECONDS)
                )
            session.add(task)
            changed += 1
        session.commit()
    return changed


def run_forever() -> None:
    while True:
        run_once()
        time.sleep(max(1, get_settings().worker_lease_seconds // 3))


if __name__ == "__main__":
    run_forever()
