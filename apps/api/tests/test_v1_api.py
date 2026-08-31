from collections.abc import Generator
from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.control.models import ControlTask
from app.db import create_db_and_tables, create_db_engine, get_session
from app.main import app
from app.models import AuditEvent


def test_v1_event_proposal_requires_an_adapter_token() -> None:
    """Removing adapter token enforcement would allow anonymous event proposals."""
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/events", json={"event_type": "adapter.notice"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def _adapter_token(client: TestClient, token_file: object, scopes: list[str]) -> str:
    token_path = token_file
    client.post(
        "/api/auth/setup",
        json={
            "bootstrap_token": token_path.read_text(encoding="utf-8"),
            "password": "password-placeholder",
        },
    )
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    return client.post(
        "/api/auth/tokens",
        json={"name": "adapter", "scopes": scopes},
        headers={"Origin": "http://localhost:5173", "X-CSRF-Token": csrf},
    ).json()["token"]


def test_valid_event_proposal_is_persisted(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, token_file = auth_client
    token = _adapter_token(client, token_file, ["propose:events"])

    response = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={"event_type": "adapter.notice", "payload": {"source": "test"}},
    )

    assert response.status_code == 201
    assert response.json()["id"]


def test_unknown_action_and_unregistered_target_are_rejected(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, token_file = auth_client
    token = _adapter_token(client, token_file, ["propose:actions"])
    headers = {"Authorization": f"Bearer {token}"}

    unknown = client.post(
        "/api/v1/actions",
        headers=headers,
        json={"action_type": "unknown", "target": "payments-api"},
    )
    unregistered_target = client.post(
        "/api/v1/actions",
        headers=headers,
        json={"action_type": "get_service_health", "target": "not-registered"},
    )

    assert unknown.status_code == 403
    assert unregistered_target.status_code == 422


def test_scope_denial_precedes_action_proposal(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, token_file = auth_client
    token = _adapter_token(client, token_file, ["propose:events"])

    response = client.post(
        "/api/v1/actions",
        headers={"Authorization": f"Bearer {token}"},
        json={"action_type": "get_service_health", "target": "payments-api"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_scope"


def test_platform_self_check_proposal_creates_native_worker_safe_payload(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, engine, token_file = auth_client
    token = _adapter_token(client, token_file, ["propose:checks"])
    response = client.post(
        "/api/v1/checks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "check_type": "platform.self_check",
            "target": "local",
            "parameters": {},
            "idempotency_key": "native-self-check-contract",
        },
    )
    assert response.status_code == 201
    with Session(engine) as session:
        task = session.get(ControlTask, UUID(response.json()["id"]))
        assert task is not None
        assert task.payload == {"task_type": "platform.self_check"}
        assert task.capability == "platform.self_check"


def test_unsupported_check_proposal_is_rejected_without_orphan_task(
    auth_client: tuple[TestClient, object, object],
) -> None:
    client, engine, token_file = auth_client
    token = _adapter_token(client, token_file, ["propose:checks"])
    response = client.post(
        "/api/v1/checks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "check_type": "get_service_health",
            "target": "payments-api",
            "parameters": {},
            "idempotency_key": "unsupported-check-contract",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "unsupported_check"
    with Session(engine) as session:
        assert session.exec(select(ControlTask)).all() == []
        rejected = session.exec(
            select(AuditEvent).where(AuditEvent.event_type == "check.rejected")
        ).all()
        assert len(rejected) == 1
