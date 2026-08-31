from datetime import timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.config import get_settings
from app.control.enums import SideEffectCertainty, TaskKind, TaskOutcome, TaskStatus
from app.control.models import ControlTask, OutboxEvent
from app.control.repositories import (
    append_outbox_event,
    claim_next_task,
    complete_task,
    enqueue_task,
    renew_task_lease,
)
from app.db import create_db_and_tables, create_db_engine
from app.models import AgentRun, RunStatus
from app.repositories import AuditRepository


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


def test_expired_read_only_lease_is_requeued_with_backoff_before_reclaim() -> None:
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
        assert reclaimed is None
        session.refresh(task)
        assert task.status == TaskStatus.QUEUED
        assert task.attempts == 1
        assert task.available_at > (now + timedelta(seconds=31)).replace(tzinfo=None)
        reclaimed = claim_next_task(
            session,
            worker_id=worker_b,
            capabilities={"control.run"},
            now=task.available_at,
        )
        assert reclaimed is not None
        assert reclaimed.id == task.id
        assert reclaimed.lease_owner_id == worker_b


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


def test_claim_recovery_emits_audit_and_outbox_with_state_transition() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.CONTROL,
            payload={"task_type": "platform.self_check"},
            idempotency_key=f"claim-recovery-events:{uuid4()}",
            capability="platform.self_check",
        )
        task_id = task.id
        first = claim_next_task(
            session,
            worker_id=uuid4(),
            capabilities={"platform.self_check"},
            now=task.available_at,
        )
        assert first is not None
        lease_expiry = first.lease_expires_at
        assert lease_expiry is not None
        assert claim_next_task(
            session,
            worker_id=uuid4(),
            capabilities={"platform.self_check"},
            now=lease_expiry + timedelta(seconds=1),
        ) is None
        session.commit()

    with Session(engine) as session:
        recovered = session.get(ControlTask, task_id)
        assert recovered is not None
        assert recovered.status == TaskStatus.QUEUED
        assert [event.event_type for event in AuditRepository(session).list()] == [
            "task.lease_recovered"
        ]
        assert {
            event.event_type for event in session.exec(select(OutboxEvent)).all()
        } == {"task.lease_recovered", "task.updated"}


def test_postgres_sessions_allow_only_one_worker_to_claim_task(postgres_session_pair) -> None:
    session_a, session_b = postgres_session_pair
    task = enqueue_task(
        session_a,
        kind=TaskKind.AGENT_RUN,
        payload={},
        idempotency_key="postgres-exclusive-claim",
        capability="control.run",
    )
    session_a.commit()
    now = task.available_at

    first = claim_next_task(
        session_a, worker_id=uuid4(), capabilities={"control.run"}, now=now
    )
    second = claim_next_task(
        session_b, worker_id=uuid4(), capabilities={"control.run"}, now=now
    )

    assert first is not None
    assert first.id == task.id
    assert second is None
    session_a.rollback()
    session_b.rollback()


def test_postgres_expired_lease_recovery_requeues_then_allows_one_reclaim(
    postgres_session_pair,
) -> None:
    session_a, session_b = postgres_session_pair
    original_worker, recovery_worker, reclaim_worker, contender_worker = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    task = enqueue_task(
        session_a,
        kind=TaskKind.AGENT_RUN,
        payload={},
        idempotency_key="postgres-expired-recovery",
        capability="control.run",
    )
    session_a.commit()
    claimed_at = task.available_at
    assert claim_next_task(
        session_a,
        worker_id=original_worker,
        capabilities={"control.run"},
        now=claimed_at,
    )
    session_a.commit()

    expired_at = claimed_at + timedelta(seconds=get_settings().worker_lease_seconds + 1)
    assert (
        claim_next_task(
            session_b,
            worker_id=recovery_worker,
            capabilities={"control.run"},
            now=expired_at,
        )
        is None
    )
    session_b.commit()
    session_a.refresh(task)
    assert task.status == TaskStatus.QUEUED
    assert task.attempts == 1
    assert task.available_at > expired_at

    reclaimed = claim_next_task(
        session_a,
        worker_id=reclaim_worker,
        capabilities={"control.run"},
        now=task.available_at,
    )
    contender = claim_next_task(
        session_b,
        worker_id=contender_worker,
        capabilities={"control.run"},
        now=task.available_at,
    )

    assert reclaimed is not None
    assert reclaimed.id == task.id
    assert contender is None
    session_a.rollback()
    session_b.rollback()


@pytest.mark.parametrize("operation", ["renew", "complete"])
def test_expired_lease_rejects_owner_for_renew_and_completion(operation: str) -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    worker_id = uuid4()
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={},
            idempotency_key=f"expired-{operation}",
            capability="control.run",
        )
        now = task.available_at
        assert claim_next_task(session, worker_id=worker_id, capabilities={"control.run"}, now=now)
        expired_at = now + timedelta(seconds=31)

        if operation == "renew":
            assert not renew_task_lease(
                session,
                task_id=task.id,
                worker_id=worker_id,
                lease_version=task.lease_version,
                now=expired_at,
            )
        else:
            task.lease_expires_at = now
            session.flush()
            with pytest.raises(ValueError, match="lease"):
                complete_task(
                    session,
                    task_id=task.id,
                    worker_id=worker_id,
                    lease_version=task.lease_version,
                    outcome=TaskOutcome.SUCCEEDED,
                    result={},
                )


def test_stale_worker_cannot_renew_reclaimed_lease() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    worker_a, worker_b = uuid4(), uuid4()
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={},
            idempotency_key="stale-renewal",
            capability="control.run",
        )
        claimed_at = task.available_at
        first = claim_next_task(
            session, worker_id=worker_a, capabilities={"control.run"}, now=claimed_at
        )
        assert first is not None
        stale_version = first.lease_version
        assert claim_next_task(
            session,
            worker_id=worker_b,
            capabilities={"control.run"},
            now=claimed_at + timedelta(seconds=31),
        ) is None
        reclaimed = claim_next_task(
            session,
            worker_id=worker_b,
            capabilities={"control.run"},
            now=task.available_at,
        )
        assert reclaimed is not None
        assert not renew_task_lease(
            session,
            task_id=task.id,
            worker_id=worker_a,
            lease_version=stale_version,
            now=task.available_at,
        )
        session.refresh(task)
        assert task.lease_owner_id == worker_b
        assert task.lease_version == stale_version + 1


def test_stale_worker_cannot_complete_reclaimed_lease() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    worker_a, worker_b = uuid4(), uuid4()
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={},
            idempotency_key="stale-completion",
            capability="control.run",
        )
        claimed_at = task.available_at
        first = claim_next_task(
            session, worker_id=worker_a, capabilities={"control.run"}, now=claimed_at
        )
        assert first is not None
        stale_version = first.lease_version
        assert claim_next_task(
            session,
            worker_id=worker_b,
            capabilities={"control.run"},
            now=claimed_at + timedelta(seconds=31),
        ) is None
        reclaimed = claim_next_task(
            session,
            worker_id=worker_b,
            capabilities={"control.run"},
            now=task.available_at,
        )
        assert reclaimed is not None
        with pytest.raises(ValueError, match="lease"):
            complete_task(
                session,
                task_id=task.id,
                worker_id=worker_a,
                lease_version=stale_version,
                outcome=TaskOutcome.SUCCEEDED,
                result={"stale": True},
            )
        session.refresh(task)
        assert task.status == TaskStatus.LEASED
        assert task.lease_owner_id == worker_b
        assert task.result is None


def test_rollback_discards_domain_mutation_and_outbox_event() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        run = AgentRun(user_request="inspect", provider="mock", model="mock")
        session.add(run)
        session.commit()
        try:
            run.status = RunStatus.RUNNING
            append_outbox_event(
                session,
                event_type="run.updated",
                resource_type="run",
                resource_id=run.id,
                payload={"status": "running"},
            )
            raise RuntimeError("simulated transaction failure")
        except RuntimeError:
            session.rollback()

        session.refresh(run)
        assert run.status == RunStatus.QUEUED
        assert session.exec(select(OutboxEvent)).all() == []
