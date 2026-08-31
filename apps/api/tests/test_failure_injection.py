from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from app.control.enums import SideEffectCertainty, TaskKind, TaskStatus
from app.control.models import ControlTask, WorkerExecutionGrant, WorkerRegistration
from app.control.repositories import claim_next_task, enqueue_task
from app.db import create_db_and_tables, create_db_engine, seed_demo_state
from app.models import ServiceState
from app.processes.control_worker import ControlWorker
from app.services.executor import ExecutionLeaseLostError, ToolExecutor
from app.services.worker_protocol import (
    PROTOCOL_VERSION,
    complete_worker_task,
    request_digest,
    start_worker_task,
)


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
    calls: list[str] = []
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

        executor = ToolExecutor(
            session,
            before_side_effect=lambda: (_ for _ in ()).throw(ExecutionLeaseLostError()),
        )
        with pytest.raises(ExecutionLeaseLostError):
            await executor.execute(action.id)
        assert calls == []
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
        task.status = TaskStatus.LEASED
        task.lease_owner_id = worker_id
        task.lease_version = 1
        task.lease_expires_at = task.available_at + timedelta(seconds=30)
        session.add(task)
        session.commit()
        digest = request_digest(task)
        start_worker_task(
            session,
            task_id=task.id,
            worker_id=worker_id,
            protocol_version=PROTOCOL_VERSION,
            request_digest_value=digest,
        )

        result = {"status": "succeeded", "detail": "fake journal result"}
        completed = complete_worker_task(
            session,
            task_id=task.id,
            worker_id=worker_id,
            protocol_version=PROTOCOL_VERSION,
            request_digest_value=digest,
            result=result,
        )
        assert completed.status is TaskStatus.SUCCEEDED
        assert completed.result == result
        assert session.get(WorkerExecutionGrant, task.id).completed_at is not None


def test_side_effect_uncertain_work_crash_becomes_manual_review() -> None:
    engine = _engine()
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.ACTION_EXECUTION,
            payload={"action": "fake"},
            idempotency_key="native-crash-after-start",
            capability="action.execute",
            side_effect_certainty=SideEffectCertainty.POSSIBLE,
        )
        session.commit()
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
        assert task.status is TaskStatus.MANUAL_REVIEW
