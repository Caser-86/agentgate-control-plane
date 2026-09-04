import json
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.control.enums import SideEffectCertainty, TaskKind, TaskStatus
from app.control.models import ControlTask, OutboxEvent
from app.db import seed_example_state
from app.models import ActionStatus, AgentRun, PolicyDecision, RiskLevel, RunStatus, ToolAction
from app.services.executor import ToolExecutor
from tests.conftest import authenticate_client


def _waiting_action(session: Session) -> ToolAction:
    run = AgentRun(
        user_request="restart after approval",
        status=RunStatus.WAITING_APPROVAL,
        provider="mock",
        model="mock-operations-agent",
        conversation_json=json.dumps([{"role": "user", "content": "restart safely"}]),
    )
    session.add(run)
    session.flush()
    action = ToolAction(
        run_id=run.id,
        tool_call_id="approval-call",
        tool_name="restart_service",
        risk_level=RiskLevel.MEDIUM,
        policy_decision=PolicyDecision.REQUIRE_APPROVAL,
        status=ActionStatus.PENDING_APPROVAL,
        arguments_json=json.dumps(
            {"service": "payments-api", "reason": "recover degraded service"}
        ),
        reason="operator approval required",
        idempotency_key=f"approval-action-{uuid4()}",
    )
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


def test_approval_does_not_execute_inside_http_request(
    auth_client: tuple[TestClient, object, object], monkeypatch
) -> None:
    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_example_state(session)
        action = _waiting_action(session)
    authenticate_client(client, token_file)
    execute = AsyncMock()
    monkeypatch.setattr(ToolExecutor, "execute", execute)

    response = client.post(f"/api/approvals/{action.id}/approve", json={"note": "approved"})

    assert response.status_code == 200
    execute.assert_not_awaited()
    with Session(engine) as session:
        task = session.exec(
            select(ControlTask).where(ControlTask.kind == TaskKind.AGENT_RUN)
        ).one()
    assert task.status == TaskStatus.QUEUED
    assert task.side_effect_certainty == SideEffectCertainty.POSSIBLE


def test_duplicate_approval_conflicts_without_second_resume_task(
    auth_client: tuple[TestClient, object, object], monkeypatch
) -> None:
    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_example_state(session)
        action = _waiting_action(session)
    authenticate_client(client, token_file)
    monkeypatch.setattr(ToolExecutor, "execute", AsyncMock())

    first = client.post(f"/api/approvals/{action.id}/approve", json={})
    second = client.post(f"/api/approvals/{action.id}/approve", json={})

    assert first.status_code == 200
    assert second.status_code == 409
    with Session(engine) as session:
        tasks = list(
            session.exec(select(ControlTask).where(ControlTask.run_id == action.run_id)).all()
        )
        events = list(
            session.exec(select(OutboxEvent).where(OutboxEvent.resource_id == action.run_id))
        )
    assert len(tasks) == 1
    assert tasks[0].status == TaskStatus.QUEUED
    assert any(event.event_type == "task.queued" for event in events)
