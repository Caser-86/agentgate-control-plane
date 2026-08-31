import re
from collections.abc import Generator
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.models import BootstrapToken, ClientToken, Operator
from app.auth.security import verify_password
from app.db import create_db_and_tables, create_db_engine, get_session
from app.main import app
from app.models import utc_now


def test_auth_status_reports_first_run_as_unauthenticated() -> None:
    """Removing the status boundary must make first-run clients unable to discover setup state."""
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/auth/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "setup_required": True}


def _setup(client: TestClient, token_file: Path) -> None:
    response = client.post(
        "/api/auth/setup",
        json={
            "bootstrap_token": token_file.read_text(encoding="utf-8"),
            "password": "password-placeholder",
        },
    )
    assert response.status_code == 201


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    return {"Origin": "http://localhost:5173", "X-CSRF-Token": token}


def test_setup_consumes_bootstrap_hashes_password_and_sets_strict_cookie(
    auth_client: tuple[TestClient, object, Path]
) -> None:
    client, engine, token_file = auth_client
    bootstrap_token = token_file.read_text(encoding="utf-8")

    response = client.post(
        "/api/auth/setup",
        json={"bootstrap_token": bootstrap_token, "password": "password-placeholder"},
    )

    assert response.status_code == 201
    assert response.json() == {"authenticated": True, "setup_required": False}
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert bootstrap_token not in response.text
    with Session(engine) as session:
        operator = session.exec(select(Operator)).one()
        stored_bootstrap = session.exec(select(BootstrapToken)).one()
        assert operator.password_hash != "password-placeholder"
        assert verify_password(operator.password_hash, "password-placeholder")
        assert stored_bootstrap.token_digest != bootstrap_token
        assert re.fullmatch(r"[0-9a-f]{64}", stored_bootstrap.token_digest)
    assert not token_file.exists()


def test_bootstrap_token_is_expired_or_consumed_once(
    auth_client: tuple[TestClient, object, Path]
) -> None:
    client, engine, token_file = auth_client
    token = token_file.read_text(encoding="utf-8")
    with Session(engine) as session:
        stored = session.exec(select(BootstrapToken)).one()
        stored.expires_at = utc_now() - timedelta(seconds=1)
        session.add(stored)
        session.commit()

    expired = client.post(
        "/api/auth/setup",
        json={"bootstrap_token": token, "password": "password-placeholder"},
    )
    assert expired.status_code == 403
    assert expired.json()["error"]["code"] == "invalid_or_expired_bootstrap_token"


def test_setup_rejects_a_reused_bootstrap_token(
    auth_client: tuple[TestClient, object, Path]
) -> None:
    client, _, token_file = auth_client
    token = token_file.read_text(encoding="utf-8")
    _setup(client, token_file)

    reused = client.post(
        "/api/auth/setup",
        json={"bootstrap_token": token, "password": "password-placeholder"},
    )

    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "setup_already_completed"


def test_bootstrap_issuance_slot_is_unique_in_the_database(
    auth_client: tuple[TestClient, object, Path]
) -> None:
    _, engine, _ = auth_client
    with Session(engine) as session:
        original = session.exec(select(BootstrapToken)).one()
        session.add(
            BootstrapToken(
                token_digest="digest-placeholder-second",
                expires_at=original.expires_at,
                issuance_key="bootstrap",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_state_change_without_csrf_is_rejected(
    auth_client: tuple[TestClient, object, Path]
) -> None:
    client, _, token_file = auth_client
    _setup(client, token_file)

    response = client.post("/api/approvals/00000000-0000-0000-0000-000000000001/deny", json={})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_validation_failed"


def test_logout_revokes_the_session(
    auth_client: tuple[TestClient, object, Path]
) -> None:
    client, _, token_file = auth_client
    _setup(client, token_file)

    logout = client.post("/api/auth/logout", headers=_csrf_headers(client))

    assert logout.status_code == 204
    assert client.get("/api/auth/status").json()["authenticated"] is False


def test_token_rotation_and_revocation_keep_only_digests(
    auth_client: tuple[TestClient, object, Path]
) -> None:
    client, engine, token_file = auth_client
    _setup(client, token_file)
    headers = _csrf_headers(client)
    created = client.post(
        "/api/auth/tokens", json={"name": "adapter", "scopes": ["propose:events"]}, headers=headers
    )
    first_token = created.json()["token"]
    first_id = created.json()["id"]
    with Session(engine) as session:
        stored = session.get(ClientToken, UUID(first_id))
        assert stored is not None
        assert stored.token_digest != first_token

    rotated = client.post(
        "/api/auth/tokens",
        json={"name": "adapter-rotated", "scopes": ["propose:events"], "rotate_token_id": first_id},
        headers=headers,
    )
    replacement_token = rotated.json()["token"]
    replacement_id = rotated.json()["id"]
    old_use = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {first_token}"},
        json={"event_type": "adapter.notice"},
    )
    revoked = client.delete(f"/api/auth/tokens/{replacement_id}", headers=headers)
    revoked_use = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {replacement_token}"},
        json={"event_type": "adapter.notice"},
    )

    assert created.status_code == 201
    assert rotated.status_code == 201
    assert old_use.status_code == 401
    assert revoked.status_code == 204
    assert revoked_use.status_code == 401
