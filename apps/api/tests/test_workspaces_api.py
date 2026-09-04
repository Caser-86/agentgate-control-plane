from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from tests.conftest import authenticate_client


def test_create_workspace_rejects_root_outside_allowed_root(
    auth_client: tuple[TestClient, object, Path], monkeypatch, tmp_path: Path
) -> None:
    client, _, token_file = auth_client
    authenticate_client(client, token_file)
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(get_settings(), "workspace_allowed_root", str(allowed))

    response = client.post(
        "/api/v1/workspaces",
        json={"name": "越界工作区", "root_path": str(outside)},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "workspace_root_not_allowed"


def test_workspace_update_increments_version_and_disable_blocks_actions(
    auth_client: tuple[TestClient, object, Path], monkeypatch, tmp_path: Path
) -> None:
    client, _, token_file = auth_client
    authenticate_client(client, token_file)
    allowed = tmp_path / "allowed"
    root = allowed / "project"
    root.mkdir(parents=True)
    monkeypatch.setattr(get_settings(), "workspace_allowed_root", str(allowed))
    created = client.post(
        "/api/v1/workspaces", json={"name": "演示工作区", "root_path": str(root)}
    )
    assert created.status_code == 201

    response = client.patch(
        f"/api/v1/workspaces/{created.json()['id']}", json={"enabled": False}
    )

    assert response.status_code == 200
    assert response.json()["version"] == created.json()["version"] + 1
    assert response.json()["enabled"] is False


def test_workspace_quarantine_endpoint_never_returns_absolute_paths(
    auth_client: tuple[TestClient, object, Path], monkeypatch, tmp_path: Path
) -> None:
    client, _, token_file = auth_client
    authenticate_client(client, token_file)
    allowed = tmp_path / "allowed"
    root = allowed / "project"
    root.mkdir(parents=True)
    monkeypatch.setattr(get_settings(), "workspace_allowed_root", str(allowed))
    created = client.post(
        "/api/v1/workspaces", json={"name": "演示工作区", "root_path": str(root)}
    )
    workspace_id = created.json()["id"]

    response = client.get(f"/api/v1/workspaces/{workspace_id}/quarantine")

    assert response.status_code == 200
    assert response.json()["items"] == []
