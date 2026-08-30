from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import create_db_and_tables, create_db_engine, get_session, seed_demo_state
from app.main import app


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        seed_demo_state(session)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


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
        json={"actor": "local-user", "note": "Reviewed the impact."},
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
