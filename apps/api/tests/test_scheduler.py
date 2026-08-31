from datetime import timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session, select

import app.processes.scheduler as scheduler
from app.control.enums import TaskKind, TaskStatus
from app.control.models import ControlTask, OutboxEvent
from app.control.repositories import enqueue_task
from app.db import create_db_and_tables, create_db_engine
from app.models import AgentRun, RunStatus, utc_now
from app.repositories import AuditRepository


def test_scheduler_enqueues_each_due_task_once(monkeypatch) -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    monkeypatch.setattr(scheduler, "get_engine", lambda: engine)
    due_task = {
        "kind": TaskKind.CONTROL,
        "payload": {"task_type": "platform.self_check"},
        "idempotency_key": "scheduled:self-check:once",
        "capability": "platform.self_check",
    }

    assert scheduler.enqueue_due_tasks([due_task]) == 1
    assert scheduler.enqueue_due_tasks([due_task]) == 0

    with Session(engine) as session:
        tasks = session.exec(select(ControlTask)).all()
    assert len(tasks) == 1
    assert tasks[0].idempotency_key == "scheduled:self-check:once"


def test_run_once_discovers_queued_run_and_enqueues_resume_once(monkeypatch) -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    monkeypatch.setattr(scheduler, "get_engine", lambda: engine)
    run = AgentRun(
        user_request="repair queued work",
        status=RunStatus.QUEUED,
        provider="mock",
        model="mock-model",
    )
    with Session(engine) as session:
        session.add(run)
        session.commit()
        run_id = run.id

    assert scheduler.run_once() == 1
    assert scheduler.run_once() == 0

    with Session(engine) as session:
        tasks = session.exec(select(ControlTask).where(ControlTask.run_id == run_id)).all()
    assert len(tasks) == 1
    assert tasks[0].kind is TaskKind.AGENT_RUN
    assert tasks[0].payload == {"run_id": str(run_id)}


def test_run_forever_executes_the_database_scheduler_entry_once(monkeypatch) -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    monkeypatch.setattr(scheduler, "get_engine", lambda: engine)
    run = AgentRun(
        user_request="run through scheduler loop",
        status=RunStatus.QUEUED,
        provider="mock",
        model="mock-model",
    )
    with Session(engine) as session:
        session.add(run)
        session.commit()
        run_id = run.id

    def stop_after_one_iteration(_: float) -> None:
        raise RuntimeError("stop test loop")

    monkeypatch.setattr(scheduler.time, "sleep", stop_after_one_iteration)
    with pytest.raises(RuntimeError, match="stop test loop"):
        scheduler.run_forever()

    with Session(engine) as session:
        tasks = session.exec(select(ControlTask).where(ControlTask.run_id == run_id)).all()
    assert len(tasks) == 1


def test_scheduler_recovers_an_expired_read_only_lease(monkeypatch) -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    monkeypatch.setattr(scheduler, "get_engine", lambda: engine)
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.CONTROL,
            payload={"task_type": "platform.self_check"},
            idempotency_key=f"expired:{uuid4()}",
            capability="platform.self_check",
        )
        task.status = TaskStatus.LEASED
        task.lease_expires_at = utc_now() - timedelta(seconds=1)
        task_id = task.id
        session.add(task)
        session.commit()

    assert scheduler.run_once() == 1

    with Session(engine) as session:
        recovered = session.get(ControlTask, task_id)
        assert recovered is not None
        assert recovered.status is TaskStatus.QUEUED
        assert recovered.lease_owner_id is None


def test_scheduler_recovery_is_guarded_by_captured_lease_snapshot() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    worker_id = uuid4()
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.CONTROL,
            payload={"task_type": "platform.self_check"},
            idempotency_key=f"race:{uuid4()}",
            capability="platform.self_check",
        )
        task.status = TaskStatus.LEASED
        task.lease_owner_id = worker_id
        task.lease_version = 4
        task.lease_expires_at = utc_now() - timedelta(seconds=1)
        session.add(task)
        session.commit()
        task_id = task.id

    with Session(engine) as stale_session:
        snapshot = stale_session.get(ControlTask, task_id)
        assert snapshot is not None
        captured_owner = snapshot.lease_owner_id
        captured_version = snapshot.lease_version
        captured_status = snapshot.status
        captured_expiry = snapshot.lease_expires_at

    with Session(engine) as winner_session:
        winner = winner_session.get(ControlTask, task_id)
        assert winner is not None
        winner.status = TaskStatus.LEASED
        winner.lease_owner_id = uuid4()
        winner.lease_version = captured_version + 1
        winner.lease_expires_at = utc_now() + timedelta(seconds=30)
        winner_session.add(winner)
        winner_session.commit()

    with Session(engine) as stale_session:
        changed = scheduler.recover_expired_lease(
            stale_session,
            task_id=task_id,
            worker_id=captured_owner,
            lease_version=captured_version,
            status=captured_status,
            lease_expires_at=captured_expiry,
            now=utc_now(),
        )
        stale_session.commit()
        assert changed is False

    with Session(engine) as session:
        current = session.get(ControlTask, task_id)
        assert current is not None
        assert current.lease_version == captured_version + 1
        assert current.status is TaskStatus.LEASED
        if current.run_id:
            assert AuditRepository(session).list(current.run_id) == []
        assert session.exec(select(OutboxEvent)).all() == []


def test_postgres_scheduler_recovery_race_does_not_overwrite_reclaimed_lease(
    postgres_session_pair,
) -> None:
    session_a, session_b = postgres_session_pair
    task = enqueue_task(
        session_a,
        kind=TaskKind.CONTROL,
        payload={"task_type": "platform.self_check"},
        idempotency_key=f"postgres-race:{uuid4()}",
        capability="platform.self_check",
    )
    session_a.commit()
    task_id = task.id
    task.status = TaskStatus.LEASED
    task.lease_owner_id = uuid4()
    task.lease_version = 2
    task.lease_expires_at = utc_now() - timedelta(seconds=1)
    session_a.add(task)
    session_a.commit()
    snapshot = session_a.get(ControlTask, task_id)
    assert snapshot is not None

    winner = session_b.get(ControlTask, task_id)
    assert winner is not None
    winner.lease_owner_id = uuid4()
    winner.lease_version = 3
    winner.lease_expires_at = utc_now() + timedelta(seconds=30)
    session_b.add(winner)
    session_b.commit()

    assert scheduler.recover_expired_lease(
        session_a,
        task_id=task_id,
        worker_id=snapshot.lease_owner_id,
        lease_version=snapshot.lease_version,
        status=snapshot.status,
        lease_expires_at=snapshot.lease_expires_at,
        now=utc_now(),
    ) is False
    session_a.rollback()
    current = session_b.get(ControlTask, task_id)
    assert current is not None
    assert current.lease_version == 3
    assert current.status is TaskStatus.LEASED
