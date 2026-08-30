from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import create_db_and_tables, create_db_engine, get_session, seed_demo_state
from app.main import app
from app.repositories import AuditRepository, RunRepository
from app.services.audit import AuditService


@pytest.fixture
def api_client() -> Generator[tuple[TestClient, UUID], None, None]:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        seed_demo_state(session)
        run = RunRepository(session).create("Inspect payments-api", "mock", "mock")
        run_id = run.id
        AuditService(AuditRepository(session)).append(
            run.id, "run.created", "user", {"user_request": "Inspect payments-api"}
        )

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client, run_id
    app.dependency_overrides.clear()


def test_audit_list_and_export(api_client: tuple[TestClient, UUID]) -> None:
    client, run_id = api_client
    listed = client.get(f"/api/audit?run_id={run_id}&actor=user")
    exported = client.get(f"/api/audit/export?run_id={run_id}")

    assert listed.status_code == 200
    assert listed.json()[0]["event_type"] == "run.created"
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert "attachment" in exported.headers["content-disposition"]
