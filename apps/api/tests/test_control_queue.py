from datetime import timedelta
from uuid import uuid4

from sqlmodel import Session

from app.control.enums import SideEffectCertainty, TaskKind, TaskStatus
from app.control.repositories import claim_next_task, enqueue_task
from app.db import create_db_and_tables, create_db_engine


def test_duplicate_idempotency_key_returns_one_task() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        first = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={},
            idempotency_key="same-request",
            capability="control.run",
        )
        second = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={},
            idempotency_key="same-request",
            capability="control.run",
        )

        assert second.id == first.id


def test_expired_read_only_lease_can_be_reclaimed_by_another_worker() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    worker_a, worker_b = uuid4(), uuid4()
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={},
            idempotency_key="recoverable",
            capability="control.run",
        )
        now = task.available_at
        first = claim_next_task(
            session, worker_id=worker_a, capabilities={"control.run"}, now=now
        )
        reclaimed = claim_next_task(
            session,
            worker_id=worker_b,
            capabilities={"control.run"},
            now=now + timedelta(seconds=31),
        )

        assert first is not None
        assert reclaimed is not None
        assert reclaimed.id == task.id
        assert reclaimed.lease_owner_id == worker_b
        assert reclaimed.attempts == 1


def test_expired_possible_side_effect_task_requires_manual_review() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.ACTION_EXECUTION,
            payload={},
            idempotency_key="uncertain",
            capability="action.execute",
            side_effect_certainty=SideEffectCertainty.POSSIBLE,
        )
        now = task.available_at
        assert claim_next_task(session, worker_id=uuid4(), capabilities={"action.execute"}, now=now)
        assert (
            claim_next_task(
                session,
                worker_id=uuid4(),
                capabilities={"action.execute"},
                now=now + timedelta(seconds=31),
            )
            is None
        )
        session.refresh(task)
        assert task.status == TaskStatus.MANUAL_REVIEW
