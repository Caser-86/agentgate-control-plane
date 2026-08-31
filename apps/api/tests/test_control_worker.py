import asyncio
from datetime import timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.control.enums import SideEffectCertainty, TaskKind, TaskStatus
from app.control.models import ControlTask, OutboxEvent
from app.control.repositories import claim_next_task, enqueue_task
from app.db import create_db_and_tables, create_db_engine, seed_demo_state
from app.llm.base import ModelTurn
from app.models import (
    ActionStatus,
    AgentRun,
    PolicyDecision,
    RiskLevel,
    RunStatus,
    ToolAction,
    utc_now,
)
from app.processes.control_worker import ControlWorker
from app.repositories import ActionRepository, RunRepository
from app.services.agent_loop import AgentRunner
from app.tools.registry import RegisteredTool, ToolRegistry
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


def test_worker_does_not_start_task_after_lease_expires_before_running(monkeypatch) -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        run = RunRepository(session).create("inspect service health", "mock", "mock")
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={"run_id": str(run.id)},
            idempotency_key="lease-race-before-running",
            capability="control.run",
            run_id=run.id,
        )
        session.commit()
        task_id = task.id

    worker = ControlWorker(engine, runner_factory=lambda _session: (_ for _ in ()).throw(
        AssertionError("expired task must not execute")
    ))
    claim_time = utc_now()
    expired = claim_time + timedelta(seconds=31)
    times = iter((claim_time, expired, expired, expired))
    monkeypatch.setattr(worker, "_now", lambda: next(times))
    assert worker.run_once() == 1

    with Session(engine) as session:
        task = session.get(ControlTask, task_id)
    assert task is not None
    assert task.status == TaskStatus.MANUAL_REVIEW


def test_worker_marks_lease_loss_after_possible_side_effect_without_retry() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    calls: list[str] = []
    worker_id = UUID("00000000-0000-0000-0000-000000000001")

    async def handler(_arguments, session: Session) -> dict[str, object]:
        calls.append("executed")
        task = session.exec(select(ControlTask)).one()
        task.lease_expires_at = utc_now() - timedelta(seconds=1)
        session.add(task)
        session.commit()
        await asyncio.sleep(0.1)
        return {"ok": True}

    registry = ToolRegistry()
    registered = registry.get("restart_service")
    registry.replace(
        "restart_service",
        RegisteredTool(registered.spec, registered.arguments_model, handler),
    )
    with Session(engine) as session:
        run = RunRepository(session).create("approved restart", "mock", "mock")
        action = ToolAction(
            run_id=run.id,
            tool_call_id="call-1",
            tool_name="restart_service",
            risk_level=RiskLevel.MEDIUM,
            policy_decision=PolicyDecision.REQUIRE_APPROVAL,
            status=ActionStatus.APPROVED,
            arguments_json='{"service":"payments-api","reason":"test reason"}',
            reason="approved",
            idempotency_key="lease-loss-action",
        )
        ActionRepository(session).create(action, commit=False)
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={"run_id": str(run.id)},
            idempotency_key="lease-loss-side-effect",
            capability="control.run",
            run_id=run.id,
            side_effect_certainty=SideEffectCertainty.POSSIBLE,
        )
        session.commit()
        task_id = task.id

    def runner_factory(session: Session) -> AgentRunner:
        return AgentRunner(session, provider=SlowProvider(), registry=registry)

    worker = ControlWorker(engine, worker_id=worker_id, runner_factory=runner_factory)
    assert worker.run_once() == 1

    with Session(engine) as session:
        task = session.get(ControlTask, task_id)
        action = session.exec(select(ToolAction)).one()
    assert calls == ["executed"]
    assert task is not None
    assert task.status == TaskStatus.MANUAL_REVIEW


def test_lost_lease_recovery_does_not_mark_reclaimed_owner_for_manual_review() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    worker_a, worker_b = UUID("00000000-0000-0000-0000-000000000011"), UUID(
        "00000000-0000-0000-0000-000000000012"
    )
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={"run_id": str(UUID(int=1))},
            idempotency_key="lost-lease-reclaim-race",
            capability="control.run",
            run_id=UUID(int=1),
            side_effect_certainty=SideEffectCertainty.READ_ONLY,
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
        session.commit()
        reclaimed = claim_next_task(
            session,
            worker_id=worker_b,
            capabilities={"control.run"},
            now=first.available_at,
        )
        assert reclaimed is not None
        worker = ControlWorker(engine, worker_id=worker_a)
        worker._finish_lost_lease(session, first, worker_a, stale_version)
        session.refresh(reclaimed)
        assert reclaimed.status == TaskStatus.LEASED
        assert reclaimed.lease_owner_id == worker_b
        assert reclaimed.lease_version == stale_version + 1


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
