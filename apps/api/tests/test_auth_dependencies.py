from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import create_db_and_tables, create_db_engine, get_session, seed_demo_state
from app.main import app


def test_existing_browser_route_rejects_an_unauthenticated_request() -> None:
    """Removing operator enforcement would expose the pre-auth run list."""
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        seed_demo_state(session)

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/runs")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_client_scope_cannot_access_an_operator_approval(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, token_file = auth_client
    client.post(
        "/api/auth/setup",
        json={
            "bootstrap_token": token_file.read_text(encoding="utf-8"),
            "password": "password-placeholder",
        },
    )
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    token = client.post(
        "/api/auth/tokens",
        json={"name": "propose-only", "scopes": ["propose:actions"]},
        headers={"Origin": "http://localhost:5173", "X-CSRF-Token": csrf},
    ).json()["token"]

    response = client.post(
        "/api/approvals/00000000-0000-0000-0000-000000000001/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert response.status_code == 403
