from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from app.control.enums import SideEffectCertainty, TaskKind, TaskStatus
from app.control.models import ControlTask, WorkerExecutionGrant, WorkerRegistration
from app.control.repositories import append_outbox_event, claim_next_task, enqueue_task
from app.db import create_db_and_tables, create_db_engine, seed_demo_state
from app.models import ServiceState
from app.processes.control_worker import ControlWorker
from app.services.executor import ExecutionLeaseLostError, ToolExecutor
from app.services.worker_protocol import (
    PROTOCOL_VERSION,
    claim_worker_task,
    complete_worker_task,
    request_digest,
    start_worker_task,
)
from app.tools.registry import RegisteredTool, ToolRegistry


def _engine():
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    return engine


def test_database_disconnect_before_claim_stops_execution_and_preserves_queued_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={"run_id": str(uuid4())},
            idempotency_key="db-disconnect-before-claim",
            capability="control.run",
        )
        session.commit()
        task_id = task.id

    def disconnect(*args, **kwargs):
        raise OperationalError("SELECT", {}, ConnectionError("fake database disconnect"))

    monkeypatch.setattr("app.processes.control_worker.claim_next_task", disconnect)
    worker = ControlWorker(
        engine, runner_factory=lambda _: (_ for _ in ()).throw(AssertionError("not called"))
    )
    with pytest.raises(OperationalError):
        worker.run_once()

    with Session(engine) as session:
        task = session.get(ControlTask, task_id)
        assert task is not None
        assert task.status is TaskStatus.QUEUED
        assert session.exec(select(ServiceState)).all() == []


@pytest.mark.asyncio
async def test_pre_grant_disconnect_calls_no_handler_and_leaves_auditable_safe_failure() -> None:
    engine = _engine()
    with Session(engine) as session:
        seed_demo_state(session)
        from app.models import ActionStatus, AgentRun, PolicyDecision, RiskLevel, ToolAction

        run = AgentRun(user_request="restart", provider="mock", model="mock")
        session.add(run)
        session.flush()
        action = ToolAction(
            run_id=run.id,
            tool_call_id="disconnect-before-grant",
            tool_name="restart_service",
            risk_level=RiskLevel.MEDIUM,
            policy_decision=PolicyDecision.AUTO_APPROVE,
            status=ActionStatus.APPROVED,
            arguments_json='{"service":"payments-api","reason":"fake disconnect"}',
            reason="approved for fake failure test",
            idempotency_key="pre-grant-disconnect",
        )
        session.add(action)
        session.commit()

        registry = ToolRegistry()
        registered = registry.get("restart_service")
        handler = AsyncMock(return_value={"ok": True})
        registry.replace(
            "restart_service",
            RegisteredTool(registered.spec, registered.arguments_model, handler),
        )
        executor = ToolExecutor(
            session,
            registry=registry,
            before_side_effect=lambda: (_ for _ in ()).throw(ExecutionLeaseLostError()),
        )
        with pytest.raises(ExecutionLeaseLostError):
            await executor.execute(action.id)
        handler.assert_not_awaited()
        session.refresh(action)
        assert action.status is ActionStatus.RUNNING
        assert session.get(ServiceState, "payments-api").restart_count == 0


def test_post_grant_disconnect_can_later_report_worker_journal_result() -> None:
    engine = _engine()
    worker_id = uuid4()
    with Session(engine) as session:
        session.add(
            WorkerRegistration(
                id=worker_id,
                name="fake-native",
                version="test",
                protocol_version=PROTOCOL_VERSION,
                capabilities=["platform.self_check"],
                token_digest="fake-worker-digest",
            )
        )
        task = enqueue_task(
            session,
            kind=TaskKind.CONTROL,
            payload={"task_type": "platform.self_check"},
            idempotency_key="post-grant-disconnect",
            capability="platform.self_check",
        )
        session.commit()
        task_id = task.id
        task.status = TaskStatus.LEASED
        task.lease_owner_id = worker_id
        task.lease_version = 1
        task.lease_expires_at = task.available_at + timedelta(seconds=30)
        session.add(task)
        session.commit()
        digest = request_digest(task)
        start_worker_task(
            session,
            task_id=task_id,
            worker_id=worker_id,
            protocol_version=PROTOCOL_VERSION,
            request_digest_value=digest,
        )
        session.close()

        result = {"status": "succeeded", "detail": "fake journal result"}
        with Session(engine) as reconnected_api:
            completed = complete_worker_task(
                reconnected_api,
                task_id=task_id,
                worker_id=worker_id,
                protocol_version=PROTOCOL_VERSION,
                request_digest_value=digest,
                result=result,
            )
            assert completed.status is TaskStatus.SUCCEEDED
            assert completed.result == result
        with Session(engine) as check:
            grant = check.get(WorkerExecutionGrant, task_id)
            assert grant is not None
            assert grant.completed_at is not None


def test_control_worker_crash_before_completion_is_recoverable_without_handler_call() -> None:
    engine = _engine()
    with Session(engine) as session:
        from app.models import AgentRun

        run = AgentRun(user_request="fake control run", provider="mock", model="mock")
        session.add(run)
        session.flush()
        task = enqueue_task(
            session,
            kind=TaskKind.AGENT_RUN,
            payload={"run_id": str(run.id)},
            idempotency_key="control-worker-crash-before-completion",
            capability="control.run",
            run_id=run.id,
        )
        session.commit()
        task_id = task.id

    def crashed_runner(_session):
        raise RuntimeError("fake control worker crash")

    with pytest.raises(RuntimeError, match="fake control worker crash"):
        ControlWorker(engine, runner_factory=crashed_runner).run_once()
    with Session(engine) as session:
        crashed = session.get(ControlTask, task_id)
        assert crashed is not None
        assert crashed.status is TaskStatus.RUNNING
        assert crashed.lease_expires_at is not None
        assert claim_next_task(
            session,
            worker_id=uuid4(),
            capabilities={"control.run"},
            now=crashed.lease_expires_at + timedelta(seconds=1),
        ) is None
        session.refresh(crashed)
        assert crashed.status is TaskStatus.QUEUED
        assert crashed.attempts == 1


def test_browser_sse_reconnect_reads_only_outbox_events_after_cursor(
    auth_client: tuple[TestClient, object, object],
) -> None:
    client, engine, token_file = auth_client
    with Session(engine) as session:
        from app.repositories import RunRepository

        run = RunRepository(session).create("fake SSE run", "mock", "mock")
        first = append_outbox_event(
            session,
            event_type="run.updated",
            resource_type="run",
            resource_id=run.id,
            payload={"status": "running"},
        )
        second = append_outbox_event(
            session,
            event_type="action.updated",
            resource_type="run",
            resource_id=run.id,
            payload={"status": "pending_approval"},
        )
        session.commit()
        run_id = run.id
        first_id = first.sequence or 0
        second_id = second.sequence or 0

    from tests.conftest import authenticate_client

    authenticate_client(client, token_file)
    with client.stream("GET", f"/api/runs/{run_id}/events?after=0&limit=2") as initial:
        initial_body = "\n".join(initial.iter_lines())
    with client.stream(
        "GET", f"/api/runs/{run_id}/events?after={first_id}&limit=1"
    ) as reconnected:
        reconnected_body = "\n".join(reconnected.iter_lines())

    assert initial.status_code == 200
    assert f"id: {first_id}" in initial_body
    assert f"id: {second_id}" in initial_body
    assert f"id: {first_id}" not in reconnected_body
    assert f"id: {second_id}" in reconnected_body


def test_duplicate_approval_conflicts_without_an_extra_task(
    auth_client: tuple[TestClient, object, object],
) -> None:
    from app.db import seed_demo_state
    from app.repositories import AuditRepository
    from tests.conftest import authenticate_client
    from tests.test_security_regressions import _pending_action

    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_demo_state(session)
        action = _pending_action(session)
    authenticate_client(client, token_file)
    first = client.post(f"/api/approvals/{action.id}/deny", json={})
    duplicate = client.post(f"/api/approvals/{action.id}/deny", json={})
    assert first.status_code == 200
    assert duplicate.status_code == 409
    with Session(engine) as session:
        tasks = session.exec(select(ControlTask).where(ControlTask.run_id == action.run_id)).all()
        assert len(tasks) == 1
        assert (
            len(
                [
                    event
                    for event in AuditRepository(session).list(action.run_id)
                    if event.event_type == "approval.denied"
                ]
            )
            == 1
        )


def test_side_effect_uncertain_work_crash_becomes_manual_review(tmp_path) -> None:
    """A native Worker crash is injected only after API start/grant is durable."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))
    from agentgate_worker.journal import WorkerJournal

    engine = _engine()
    worker_id = uuid4()
    journal = WorkerJournal(tmp_path / "native-worker-journal.db")
    host_calls: list[str] = []

    def noop_handler() -> None:
        host_calls.append("must not run")

    with Session(engine) as session:
        session.add(
            WorkerRegistration(
                id=worker_id,
                name="fake-native-crash-worker",
                version="test",
                protocol_version=PROTOCOL_VERSION,
                capabilities=["platform.self_check"],
                token_digest="fake-native-worker-digest",
            )
        )
        task = enqueue_task(
            session,
            kind=TaskKind.CONTROL,
            payload={"task_type": "platform.self_check"},
            idempotency_key="native-crash-after-start",
            capability="platform.self_check",
            side_effect_certainty=SideEffectCertainty.POSSIBLE,
        )
        session.commit()
        claimed = claim_worker_task(
            session,
            worker_id=worker_id,
            protocol_version=PROTOCOL_VERSION,
            capabilities=["platform.self_check"],
        )
        assert claimed is not None
        digest = request_digest(claimed)
        start_worker_task(
            session,
            task_id=claimed.id,
            worker_id=worker_id,
            protocol_version=PROTOCOL_VERSION,
            request_digest_value=digest,
        )
        session.refresh(task)
        assert task.status is TaskStatus.RUNNING
        assert session.get(WorkerExecutionGrant, task.id) is not None
        assert callable(noop_handler)  # Phase 0 protocol has no host-side dispatch.

        # The native Worker has started its no-op handler and durably journaled
        # uncertainty; the connection-loss seam models a process crash before
        # the completion/report request can reach the API.
        journal.record_started(str(task.id), digest, task.lease_expires_at)
        journal.record_result(
            str(task.id), {"status": "unknown", "detail": "crashed after start"}
        )

        class NativeWorkerConnectionLost(RuntimeError):
            pass

        with pytest.raises(NativeWorkerConnectionLost, match="after start"):
            raise NativeWorkerConnectionLost("native Worker connection lost after start")

        assert journal.pending_reports() == [
            (str(task.id), digest, {"status": "unknown", "detail": "crashed after start"})
        ]
        started_events = session.exec(
            select(ControlTask).where(ControlTask.id == task.id)
        ).one()
        assert started_events.started_at is not None

        lease_expires_at = task.lease_expires_at
        assert lease_expires_at is not None
        recovery_now = lease_expires_at + timedelta(seconds=1)
        assert claim_next_task(
            session,
            worker_id=uuid4(),
            capabilities={"platform.self_check"},
            now=recovery_now,
        ) is None
        session.refresh(task)
        assert task.status is TaskStatus.MANUAL_REVIEW
        assert task.result is None
        assert host_calls == []
