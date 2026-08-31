from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.control.models import ControlTask, OutboxEvent
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


def test_check_status_reads_the_submitted_task_with_check_scope(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, token_file = auth_client
    token = _adapter_token(client, token_file, ["propose:checks"])
    response = client.post(
        "/api/v1/checks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "check_type": "platform.self_check",
            "target": "local",
            "parameters": {},
            "idempotency_key": "check-status-contract",
        },
    )
    assert response.status_code == 201
    check_id = response.json()["id"]

    status = client.get(
        f"/api/v1/checks/{check_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert status.status_code == 200
    assert status.json()["id"] == check_id
    assert status.json()["status"] == "queued"


def test_check_status_and_idempotency_are_scoped_to_submitter(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, engine, token_file = auth_client
    first_token = _adapter_token(client, token_file, ["propose:checks"])
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    second_token = client.post(
        "/api/auth/tokens",
        json={"name": "second-adapter", "scopes": ["propose:checks"]},
        headers={"Origin": "http://localhost:5173", "X-CSRF-Token": csrf},
    ).json()["token"]
    payload = {
        "check_type": "platform.self_check",
        "target": "local",
        "parameters": {},
        "idempotency_key": "same-key-two-clients",
    }
    first = client.post(
        "/api/v1/checks", headers={"Authorization": f"Bearer {first_token}"}, json=payload
    )
    second = client.post(
        "/api/v1/checks", headers={"Authorization": f"Bearer {second_token}"}, json=payload
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]
    hidden = client.get(
        f"/api/v1/checks/{first.json()['id']}",
        headers={"Authorization": f"Bearer {second_token}"},
    )
    assert hidden.status_code == 404
    assert "task" not in hidden.text.lower()
    with Session(engine) as session:
        assert len(session.exec(select(ControlTask)).all()) == 2


def test_successful_check_proposal_has_atomic_audit_and_queue_event(
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
            "idempotency_key": "atomic-check-proposal",
        },
    )
    assert response.status_code == 201
    task_id = UUID(response.json()["id"])
    with Session(engine) as session:
        events = session.exec(
            select(OutboxEvent).where(OutboxEvent.resource_id == task_id)
        ).all()
        audits = session.exec(
            select(AuditEvent).where(AuditEvent.resource_id == task_id)
        ).all()
        assert {event.event_type for event in events} == {"task.queued", "check.accepted"}
        assert [audit.event_type for audit in audits] == ["check.accepted"]


def test_check_proposal_rolls_back_task_when_observability_fails(
    auth_client: tuple[TestClient, object, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, engine, token_file = auth_client
    token = _adapter_token(client, token_file, ["propose:checks"])

    def fail_append(*args: object, **kwargs: object) -> object:
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr("app.api.v1.AuditService.append", fail_append)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        client.post(
            "/api/v1/checks",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "check_type": "platform.self_check",
                "target": "local",
                "parameters": {},
                "idempotency_key": "rollback-check-proposal",
            },
        )
    with Session(engine) as session:
        assert session.exec(select(ControlTask)).all() == []
        assert session.exec(select(OutboxEvent)).all() == []


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


@pytest.mark.parametrize(
    ("target", "parameters"), [("payments-api", {}), ("local", {"extra": True})]
)
def test_platform_self_check_rejects_non_local_target_and_parameters(
    auth_client: tuple[TestClient, object, object], target: str, parameters: dict[str, object]
) -> None:
    client, engine, token_file = auth_client
    token = _adapter_token(client, token_file, ["propose:checks"])
    response = client.post(
        "/api/v1/checks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "check_type": "platform.self_check",
            "target": target,
            "parameters": parameters,
            "idempotency_key": f"invalid-self-check-{target}-{bool(parameters)}",
        },
    )
    assert response.status_code == 403
    with Session(engine) as session:
        assert session.exec(select(ControlTask)).all() == []
