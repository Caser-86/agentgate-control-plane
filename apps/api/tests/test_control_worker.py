import asyncio
from datetime import timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.control.enums import SideEffectCertainty, TaskKind, TaskStatus
from app.control.models import ControlTask, OutboxEvent
from app.control.repositories import enqueue_task
from app.db import create_db_and_tables, create_db_engine, seed_demo_state
from app.llm.base import ModelTurn
from app.models import AgentRun, RunStatus, utc_now
from app.processes.control_worker import ControlWorker
from app.repositories import RunRepository
from app.services.agent_loop import AgentRunner
from tests.conftest import authenticate_client


def test_worker_recovers_queued_run_after_api_process_exits(
    auth_client: tuple[TestClient, object, object],
) -> None:
    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_demo_state(session)
    authenticate_client(client, token_file)
    response = client.post("/api/runs", json={"user_request": "inspect orders-api health"})
    run_id = UUID(response.json()["id"])

    assert ControlWorker(engine).run_once() == 1

    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        task = session.exec(select(ControlTask).where(ControlTask.run_id == run_id)).one()
    assert run is not None
    assert run.status == RunStatus.COMPLETED
    assert task.status == TaskStatus.SUCCEEDED


def test_worker_marks_malformed_control_task_for_manual_review() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={"unexpected": "payload"},
            idempotency_key="malformed-run-task",
            capability="control.run",
        )
        session.commit()
        task_id = task.id

    assert ControlWorker(engine).run_once() == 1

    with Session(engine) as session:
        task = session.get(ControlTask, task_id)
    assert task is not None
    assert task.status == TaskStatus.MANUAL_REVIEW
    assert task.error_class == "invalid_control_task"


def test_expired_possible_run_task_requires_manual_review_instead_of_reexecution() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    first_worker = ControlWorker(engine)
    with Session(engine) as session:
        run = RunRepository(session).create("inspect service health", "mock", "mock")
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={"run_id": str(run.id)},
            idempotency_key="possible-restart-resume",
            capability="control.run",
            run_id=run.id,
            side_effect_certainty=SideEffectCertainty.POSSIBLE,
        )
        session.commit()
        task_id = task.id
        assert first_worker.run_once() == 1
        session.refresh(task)
        task = session.get(ControlTask, task_id)
        assert task is not None
        task.status = TaskStatus.RUNNING
        task.lease_expires_at = utc_now() - timedelta(seconds=1)
        session.add(task)
        session.commit()

    assert ControlWorker(engine).run_once() == 0

    with Session(engine) as session:
        task = session.get(ControlTask, task_id)
    assert task is not None
    assert task.status == TaskStatus.MANUAL_REVIEW


class SlowProvider:
    async def complete(self, messages, tools) -> ModelTurn:
        del messages, tools
        await asyncio.sleep(0.05)
        return ModelTurn({"role": "assistant", "content": "late"}, "late", ())


def test_provider_timeout_records_failed_run_task_and_durable_events() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        run = RunRepository(session).create("inspect service health", "mock", "mock")
        RunRepository(session).save_checkpoint(
            run.id, [{"role": "user", "content": "inspect service health"}], 0
        )
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={"run_id": str(run.id)},
            idempotency_key="timeout-run-task",
            capability="control.run",
            run_id=run.id,
        )
        session.commit()
        run_id, task_id = run.id, task.id

    def slow_runner(session: Session) -> AgentRunner:
        return AgentRunner(session, provider=SlowProvider(), run_timeout_seconds=0.001)

    assert ControlWorker(engine, runner_factory=slow_runner).run_once() == 1

    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        task = session.get(ControlTask, task_id)
        events = list(session.exec(select(OutboxEvent).where(OutboxEvent.resource_id == run_id)))
    assert run is not None
    assert task is not None
    assert run.status == RunStatus.FAILED
    assert task.status == TaskStatus.FAILED
    assert any(event.event_type == "run.failed" for event in events)
    assert any(event.event_type == "task.updated" for event in events)
