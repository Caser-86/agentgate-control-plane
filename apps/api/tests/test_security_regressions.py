import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.auth.models import ClientToken
from app.auth.security import digest_secret
from app.control.enums import TaskKind, TaskStatus
from app.control.models import ControlTask, WorkerExecutionGrant, WorkerRegistration
from app.control.repositories import enqueue_task
from app.db import create_db_and_tables, create_db_engine, seed_demo_state
from app.llm.base import ModelTurn, ToolCall
from app.models import ActionStatus, PolicyDecision, RiskLevel, ToolAction
from app.repositories import ActionRepository, AuditRepository, RunRepository
from app.services.audit import AuditService
from app.services.worker_protocol import (
    PROTOCOL_VERSION,
    WorkerProtocolError,
    request_digest,
    start_worker_task,
)
from tests.conftest import authenticate_client


class ShellPayloadProvider:
    async def complete(self, messages, tools) -> ModelTurn:
        del tools
        if any(message.get("role") == "tool" for message in messages):
            return ModelTurn({"role": "assistant", "content": "safe refusal"}, "safe refusal", ())
        return ModelTurn(
            {"role": "assistant", "content": None, "tool_calls": []},
            None,
            (ToolCall("shell-1", "shell.exec", {"command": "echo fake-secret"}),),
        )


def _new_engine() -> Engine:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    return engine


def _pending_action(session: Session) -> ToolAction:
    run = RunRepository(session).create("restart safely", "mock", "mock")
    action = ToolAction(
        run_id=run.id,
        tool_call_id="approval-1",
        tool_name="restart_service",
        risk_level=RiskLevel.MEDIUM,
        policy_decision=PolicyDecision.REQUIRE_APPROVAL,
        status=ActionStatus.PENDING_APPROVAL,
        arguments_json=json.dumps({"service": "payments-api", "reason": "fake approval test"}),
        reason="operator approval required",
        idempotency_key=f"approval-{uuid4()}",
    )
    ActionRepository(session).create(action, commit=False)
    session.commit()
    session.refresh(action)
    return action


@pytest.mark.asyncio
async def test_arbitrary_shell_payload_is_denied_without_side_effect_and_audited() -> None:
    from app.services.agent_loop import AgentRunner

    engine = _new_engine()
    with Session(engine) as session:
        seed_demo_state(session)
        run_id = await AgentRunner(
            session, provider=ShellPayloadProvider(), run_timeout_seconds=5
        ).start_run("investigate without shell")
        action = ActionRepository(session).list_for_run(run_id)[0]
        events = AuditRepository(session).list(run_id)
        tasks = session.exec(select(ControlTask).where(ControlTask.run_id == run_id)).all()

        assert action.status is ActionStatus.DENIED
        assert json.loads(action.result_json or "{}")["error"] == "unknown tool denied"
        from app.models import ServiceState

        assert session.get(ServiceState, "payments-api").restart_count == 0
        assert not tasks
        assert any(event.event_type == "tool.denied" for event in events)
        assert "fake-secret" not in " ".join(event.payload_json for event in events)


def test_secret_like_keys_are_redacted_at_audit_and_api_boundaries() -> None:
    engine = _new_engine()
    fake_secret = "fake-api-key-for-regression-only"
    with Session(engine) as session:
        run = RunRepository(session).create("inspect", "mock", "mock")
        action = ToolAction(
            run_id=run.id,
            tool_call_id="redact-1",
            tool_name="restart_service",
            risk_level=RiskLevel.MEDIUM,
            policy_decision=PolicyDecision.REQUIRE_APPROVAL,
            status=ActionStatus.PENDING_APPROVAL,
            arguments_json=json.dumps(
                {
                    "API_KEY": fake_secret,
                    "client_secret": fake_secret,
                    "nested": {"Token": fake_secret},
                }
            ),
            result_json=json.dumps({"Authorization": fake_secret, "access_token": fake_secret}),
            reason="fake redaction test",
            idempotency_key="redact-regression",
        )
        ActionRepository(session).create(action, commit=False)
        AuditService(AuditRepository(session)).append(
            run.id,
            "security.test",
            "test",
            {"Secret": fake_secret, "safe": "visible"},
            action.id,
        )

        from app.api.runs import to_action_response, to_audit_response

        action_response = to_action_response(action)
        audit_response = to_audit_response(AuditRepository(session).list(run.id)[0])
        assert fake_secret not in json.dumps(action_response.model_dump(), default=str)
        assert fake_secret not in json.dumps(audit_response.model_dump(), default=str)
        assert action_response.arguments["API_KEY"] == "***REDACTED***"
        assert action_response.arguments["client_secret"] == "***REDACTED***"


def test_expired_worker_approval_cannot_start_and_creates_no_execution_grant() -> None:
    engine = _new_engine()
    worker_id = uuid4()
    with Session(engine) as session:
        worker = WorkerRegistration(
            id=worker_id,
            name="fake-worker",
            version="test",
            protocol_version=PROTOCOL_VERSION,
            capabilities=["platform.self_check"],
            token_digest=digest_secret("fake-worker-token"),
        )
        session.add(worker)
        task = enqueue_task(
            session,
            kind=TaskKind.CONTROL,
            payload={"task_type": "platform.self_check"},
            idempotency_key="expired-worker-task",
            capability="platform.self_check",
        )
        session.commit()
        task.lease_owner_id = worker_id
        task.lease_version = 1
        task.status = TaskStatus.LEASED
        task.lease_expires_at = task.available_at - timedelta(seconds=1)
        session.add(task)
        session.commit()

        with pytest.raises(WorkerProtocolError, match="lease_expired"):
            start_worker_task(
                session,
                task_id=task.id,
                worker_id=worker_id,
                protocol_version=PROTOCOL_VERSION,
                request_digest_value=request_digest(task),
            )
        assert session.get(WorkerExecutionGrant, task.id) is None
        session.refresh(task)
        assert task.status is TaskStatus.LEASED


def test_parameter_digest_mismatch_cannot_start_or_mutate_task() -> None:
    engine = _new_engine()
    worker_id = uuid4()
    with Session(engine) as session:
        session.add(
            WorkerRegistration(
                id=worker_id,
                name="fake-worker",
                version="test",
                protocol_version=PROTOCOL_VERSION,
                capabilities=["platform.self_check"],
                token_digest=digest_secret("fake-worker-token-2"),
            )
        )
        task = enqueue_task(
            session,
            kind=TaskKind.CONTROL,
            payload={"task_type": "platform.self_check"},
            idempotency_key="digest-mismatch",
            capability="platform.self_check",
        )
        session.commit()
        task.lease_owner_id = worker_id
        task.lease_version = 1
        task.status = TaskStatus.LEASED
        task.lease_expires_at = task.available_at + timedelta(seconds=30)
        session.add(task)
        session.commit()

        with pytest.raises(WorkerProtocolError, match="request_digest_mismatch"):
            start_worker_task(
                session,
                task_id=task.id,
                worker_id=worker_id,
                protocol_version=PROTOCOL_VERSION,
                request_digest_value="0" * 64,
            )
        assert session.get(WorkerExecutionGrant, task.id) is None
        session.refresh(task)
        assert task.status is TaskStatus.LEASED


def test_unscoped_client_token_cannot_approve_pending_action(
    auth_client: tuple[TestClient, Engine, object],
) -> None:
    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_demo_state(session)
        action = _pending_action(session)
        session.add(
            ClientToken(
                name="fake-propose-only",
                token_digest=digest_secret("fake-propose-token"),
                scopes=["runs:read"],
            )
        )
        session.commit()
        before_audit = len(AuditRepository(session).list(action.run_id))
    authenticate_client(client, token_file)
    client.cookies.clear()
    response = client.post(
        f"/api/approvals/{action.id}/approve",
        headers={"Authorization": "Bearer fake-propose-token"},
        json={},
    )

    assert response.status_code == 403
    with Session(engine) as session:
        persisted = session.get(ToolAction, action.id)
        assert persisted is not None
        assert persisted.status is ActionStatus.PENDING_APPROVAL
        assert (
            session.exec(select(ControlTask).where(ControlTask.run_id == action.run_id)).all() == []
        )
        assert len(AuditRepository(session).list(action.run_id)) == before_audit
