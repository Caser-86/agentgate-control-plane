from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.control.models import ControlTask
from app.db import create_db_and_tables, create_db_engine
from app.files.models import ManagedWorkspace
from app.models import ActionStatus, ToolAction
from app.schemas_actions import ExternalActionRequest
from app.services.file_actions import ExternalActionService
from tests.conftest import authenticate_client


@pytest.fixture
def session(tmp_path: Path) -> Generator[Session, None, None]:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as database_session:
        database_session.add(
            ManagedWorkspace(
                id=uuid4(),
                name="测试工作区",
                root_path=str(tmp_path),
                canonical_root_path=str(tmp_path),
                quarantine_root_path=str(tmp_path.parent / "quarantine"),
                protected_patterns=[".git/**", ".env", "protected/**"],
                enabled=True,
                version=1,
            )
        )
        database_session.commit()
        yield database_session


@pytest.fixture
def workspace_id(session: Session) -> object:
    return session.exec(select(ManagedWorkspace.id)).one()


def test_protected_quarantine_is_persisted_as_denied_without_task(
    session: Session, workspace_id: object
) -> None:
    client_id = uuid4()
    response = ExternalActionService(session).propose(
        client_id,
        ExternalActionRequest(
            action="file.quarantine.v1", workspace_id=workspace_id, relative_path=".env"
        ),
        "deny-protected-1",
    )

    assert response.decision == "deny"
    assert response.status == ActionStatus.DENIED.value
    assert session.exec(select(ControlTask)).all() == []


def test_inspect_is_queued_with_structured_payload(
    session: Session, workspace_id: object
) -> None:
    response = ExternalActionService(session).propose(
        uuid4(),
        ExternalActionRequest(
            action="file.inspect.v1", workspace_id=workspace_id, relative_path="notes.txt"
        ),
        "inspect-1",
    )

    task = session.exec(select(ControlTask)).one()
    assert response.decision == "allow_auto"
    assert response.status == ActionStatus.AUTO_APPROVED.value
    assert task.capability == "file.inspect.v1"
    assert task.payload["relative_path"] == "notes.txt"
    assert "root_path" not in task.payload


def test_same_client_idempotency_key_returns_same_action(
    session: Session, workspace_id: object
) -> None:
    client_id = uuid4()
    request = ExternalActionRequest(
        action="file.inspect.v1", workspace_id=workspace_id, relative_path="notes.txt"
    )
    first = ExternalActionService(session).propose(client_id, request, "same-key")
    second = ExternalActionService(session).propose(client_id, request, "same-key")

    assert second.id == first.id
    assert second.task_id == first.task_id
    assert len(session.exec(select(ToolAction)).all()) == 1
    assert len(session.exec(select(ControlTask)).all()) == 1


def test_same_idempotency_key_can_be_used_by_different_clients(
    session: Session, workspace_id: object
) -> None:
    request = ExternalActionRequest(
        action="file.inspect.v1", workspace_id=workspace_id, relative_path="notes.txt"
    )

    first = ExternalActionService(session).propose(uuid4(), request, "shared-key")
    second = ExternalActionService(session).propose(uuid4(), request, "shared-key")

    assert second.id != first.id


def test_external_rest_action_returns_persisted_status_and_can_be_read_by_submitter(
    auth_client: tuple[TestClient, object, Path], monkeypatch, tmp_path: Path
) -> None:
    from app.config import get_settings

    client, _, token_file = auth_client
    authenticate_client(client, token_file)
    allowed = tmp_path / "allowed"
    root = allowed / "project"
    root.mkdir(parents=True)
    monkeypatch.setattr(get_settings(), "workspace_allowed_root", str(allowed))
    workspace = client.post(
        "/api/v1/workspaces", json={"name": "外部 Agent 工作区", "root_path": str(root)}
    ).json()
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    token = client.post(
        "/api/auth/tokens",
        json={"name": "external-action-test", "scopes": ["propose:actions"]},
        headers={"Origin": "http://localhost:5173", "X-CSRF-Token": csrf},
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "rest-inspect-1"}

    response = client.post(
        "/api/v1/actions",
        headers=headers,
        json={
            "action": "file.inspect.v1",
            "workspace_id": workspace["id"],
            "relative_path": "notes.txt",
        },
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "allow_auto"
    action_id = response.json()["id"]
    status = client.get(f"/api/v1/actions/{action_id}", headers=headers)
    assert status.status_code == 200
    assert status.json()["id"] == action_id
    assert status.json()["relative_path"] == "notes.txt"


def test_external_file_action_requires_idempotency_header(
    auth_client: tuple[TestClient, object, Path], monkeypatch, tmp_path: Path
) -> None:
    from app.config import get_settings

    client, _, token_file = auth_client
    authenticate_client(client, token_file)
    allowed = tmp_path / "allowed"
    root = allowed / "project"
    root.mkdir(parents=True)
    monkeypatch.setattr(get_settings(), "workspace_allowed_root", str(allowed))
    workspace = client.post(
        "/api/v1/workspaces", json={"name": "外部 Agent 工作区", "root_path": str(root)}
    ).json()
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    token = client.post(
        "/api/auth/tokens",
        json={"name": "external-action-test", "scopes": ["propose:actions"]},
        headers={"Origin": "http://localhost:5173", "X-CSRF-Token": csrf},
    ).json()["token"]

    response = client.post(
        "/api/v1/actions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "file.inspect.v1",
            "workspace_id": workspace["id"],
            "relative_path": "notes.txt",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "missing_idempotency_key"
