import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import seed_example_state
from app.repositories import AuditRepository, RunRepository
from app.services.audit import AuditService
from tests.conftest import authenticate_client


@pytest.fixture
def api_client(auth_client: tuple[TestClient, object, object]) -> tuple[TestClient, UUID]:
    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_example_state(session)
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


def test_generic_audit_list_and_export_allow_missing_run_id(
    auth_client: tuple[TestClient, object, object],
) -> None:
    client, engine, token_file = auth_client
    resource_id = uuid4()
    with Session(engine) as session:
        event = AuditService(AuditRepository(session)).append(
            event_type="worker.registered",
            actor="worker",
            payload={"resource": "local-worker", "token": "do-not-leak"},
            resource_type="worker",
            resource_id=resource_id,
        )
        event_id = event.id

    authenticate_client(client, token_file)
    listed = client.get("/api/audit")
    exported = client.get("/api/audit/export")

    assert listed.status_code == 200
    listed_event = next(item for item in listed.json() if item["id"] == str(event_id))
    assert listed_event["run_id"] is None
    assert listed_event["resource_type"] == "worker"
    assert listed_event["resource_id"] == str(resource_id)
    assert listed_event["payload"]["token"] == "***REDACTED***"
    assert exported.status_code == 200
    exported_event = next(item for item in json.loads(exported.text) if item["id"] == str(event_id))
    assert exported_event["run_id"] is None
    assert exported_event["resource_type"] == "worker"
