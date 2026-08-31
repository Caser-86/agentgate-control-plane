import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.runs import to_action_response
from app.db import seed_demo_state
from app.models import ActionStatus, PolicyDecision, RiskLevel, ToolAction
from app.services.runs import RunService
from tests.conftest import authenticate_client


@pytest.fixture
def api_client(auth_client: tuple[TestClient, object, object]) -> TestClient:
    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_demo_state(session)
    authenticate_client(client, token_file)
    return client


def test_runs_api_contract(api_client: TestClient) -> None:
    created = api_client.post("/api/runs", json={"user_request": "Inspect payments-api"})
    assert created.status_code == 202
    run_id = created.json()["id"]

    assert api_client.get("/api/runs").status_code == 200
    assert api_client.get(f"/api/runs/{run_id}").status_code == 200
    assert api_client.get(f"/api/runs/{uuid4()}").json()["error"]["code"] == "not_found"
    assert api_client.get(f"/api/runs/{uuid4()}").status_code == 404


def test_approval_api_returns_conflict_and_not_found(api_client: TestClient) -> None:
    response = api_client.post(f"/api/approvals/{uuid4()}/approve", json={})

    assert response.status_code == 404
    assert set(response.json()) == {"error"}
    assert set(response.json()["error"]) == {"code", "message"}


def test_pending_approval_can_be_approved_and_duplicate_conflicts(api_client: TestClient) -> None:
    created = api_client.post(
        "/api/runs",
        json={
            "user_request": (
                "Investigate payments-api and restore it safely. Do not rotate credentials."
            )
        },
    )
    run_id = created.json()["id"]
    detail = api_client.get(f"/api/runs/{run_id}").json()
    action = next(item for item in detail["actions"] if item["status"] == "pending_approval")

    approved = api_client.post(
        f"/api/approvals/{action['id']}/approve",
        json={"note": "Reviewed the impact."},
    )
    duplicate = api_client.post(f"/api/approvals/{action['id']}/approve", json={})

    assert approved.status_code == 200
    assert approved.json()["status"] == "succeeded"
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "approval_conflict"


def test_api_validation_uses_unified_error_shape(api_client: TestClient) -> None:
    response = api_client.post("/api/runs", json={"user_request": "bad"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_provider_error_does_not_return_the_provider_exception(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_create(
        _: RunService, __: str, ___: object
    ) -> object:
        raise RuntimeError("provider-exception-placeholder")

    monkeypatch.setattr(RunService, "create", fail_create)

    response = api_client.post("/api/runs", json={"user_request": "Inspect payments-api"})

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "provider_error", "message": "Provider unavailable"}
    }
    assert "provider-exception-placeholder" not in response.text


def test_run_detail_redacts_sensitive_action_fields(api_client: TestClient) -> None:
    action = ToolAction(
        run_id=uuid4(),
        tool_call_id="call-redact",
        tool_name="ops.restart_service",
        risk_level=RiskLevel.HIGH,
        policy_decision=PolicyDecision.REQUIRE_APPROVAL,
        status=ActionStatus.PENDING_APPROVAL,
        arguments_json=json.dumps(
            {"service": "payments-api", "api_key": "secret", "nested": {"token": "value"}}
        ),
        result_json=json.dumps({"authorization": "credential-placeholder"}),
        idempotency_key="redaction-test",
        reason="requires human approval",
    )

    response = to_action_response(action)

    assert response.arguments == {
        "service": "payments-api",
        "api_key": "***REDACTED***",
        "nested": {"token": "***REDACTED***"},
    }
    assert response.result == {"authorization": "***REDACTED***"}
