from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import seed_demo_state
from app.repositories import AuditRepository, RunRepository
from app.services.audit import AuditService
from tests.conftest import authenticate_client


@pytest.fixture
def api_client(auth_client: tuple[TestClient, object, object]) -> tuple[TestClient, UUID]:
    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_demo_state(session)
        run = RunRepository(session).create("Inspect payments-api", "mock", "mock")
        run_id = run.id
        AuditService(AuditRepository(session)).append(
            run.id, "run.created", "user", {"user_request": "Inspect payments-api"}
        )

    authenticate_client(client, token_file)
    return client, run_id


def test_audit_list_and_export(api_client: tuple[TestClient, UUID]) -> None:
    client, run_id = api_client
    listed = client.get(f"/api/audit?run_id={run_id}&actor=user")
    exported = client.get(f"/api/audit/export?run_id={run_id}")

    assert listed.status_code == 200
    assert listed.json()[0]["event_type"] == "run.created"
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert "attachment" in exported.headers["content-disposition"]
