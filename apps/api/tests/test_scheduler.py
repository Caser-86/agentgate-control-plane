from datetime import timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session, select

import app.processes.scheduler as scheduler
from app.control.enums import TaskKind, TaskStatus
from app.control.models import ControlTask
from app.control.repositories import enqueue_task
from app.db import create_db_and_tables, create_db_engine
from app.models import AgentRun, RunStatus, utc_now


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
