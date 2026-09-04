import hashlib
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from app.config import get_settings
from tests.conftest import authenticate_client


def test_external_agent_approval_worker_and_status_form_one_closed_loop(
    auth_client: tuple[TestClient, Engine, Path], monkeypatch, tmp_path: Path
) -> None:
    client, engine, token_file = auth_client
    authenticate_client(client, token_file)
    allowed_root = tmp_path / "allowed"
    workspace_root = allowed_root / "interview-demo"
    workspace_root.mkdir(parents=True)
    (workspace_root / "demo.txt").write_bytes(b"demo")
    monkeypatch.setattr(get_settings(), "workspace_allowed_root", str(allowed_root))

    workspace_response = client.post(
        "/api/v1/workspaces",
        json={"name": "面试安全演示", "root_path": str(workspace_root)},
    )
    assert workspace_response.status_code == 201
    workspace_id = workspace_response.json()["id"]

    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    enrollment_response = client.post(
        "/api/auth/tokens",
        json={"name": "e2e-worker-enrollment", "scopes": ["worker:enroll"]},
        headers={"Origin": "http://localhost:5173", "X-CSRF-Token": csrf},
    )
    assert enrollment_response.status_code == 201
    enrollment_token = enrollment_response.json()["token"]
    worker_response = client.post(
        "/api/v1/worker/register",
        headers={"Authorization": f"Bearer {enrollment_token}"},
        json={
            "name": "e2e-file-worker",
            "version": "test",
            "protocol_version": "1.0",
            "capabilities": ["file.quarantine.v1", "file.restore.v1"],
        },
    )
    assert worker_response.status_code == 201
    worker = worker_response.json()
    worker_headers = {"Authorization": f"Bearer {worker['token']}"}

    external_token = client.post(
        "/api/auth/tokens",
        json={"name": "e2e-external-agent", "scopes": ["propose:actions"]},
        headers={"Origin": "http://localhost:5173", "X-CSRF-Token": csrf},
    ).json()["token"]
    external_headers = {
        "Authorization": f"Bearer {external_token}",
        "Idempotency-Key": "e2e-file-quarantine-1",
    }
    proposal = client.post(
        "/api/v1/actions",
        headers=external_headers,
        json={
            "action": "file.quarantine.v1",
            "workspace_id": workspace_id,
            "relative_path": "demo.txt",
            "reason": "演示人工审批后隔离",
        },
    )
    assert proposal.status_code == 200
    action_id = proposal.json()["id"]
    assert proposal.json()["status"] == "pending_approval"

    approval_csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    approved = client.post(
        f"/api/approvals/{action_id}/approve",
        json={"note": "确认目标是演示文件"},
        headers={"Origin": "http://localhost:5173", "X-CSRF-Token": approval_csrf},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    claim = client.post(
        "/api/v1/worker/claim",
        headers=worker_headers,
        json={
            "protocol_version": "1.0",
            "capabilities": ["file.quarantine.v1", "file.restore.v1"],
        },
    )
    assert claim.status_code == 200
    grant = claim.json()
    task_id = UUID(grant["task_id"])
    started = client.post(
        f"/api/v1/worker/tasks/{task_id}/start",
        headers=worker_headers,
        json={"protocol_version": "1.0", "request_digest": grant["request_digest"]},
    )
    assert started.status_code == 204
    digest = hashlib.sha256(b"demo").hexdigest()
    completed = client.post(
        f"/api/v1/worker/tasks/{task_id}/complete",
        headers=worker_headers,
        json={
            "protocol_version": "1.0",
            "request_digest": grant["request_digest"],
            "result": {
                "status": "succeeded",
                "result_kind": "file_quarantine",
                "side_effect": "quarantined",
                "content_sha256": digest,
                "size_bytes": 4,
                "quarantine_entry_id": action_id,
                "quarantine_relative_path": f"entries/{UUID(action_id).hex}/demo.txt",
            },
        },
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "succeeded"

    status = client.get(f"/api/v1/actions/{action_id}", headers=external_headers)
    assert status.status_code == 200
    assert status.json()["status"] == "succeeded"
    assert status.json()["result"]["side_effect"] == "quarantined"
    assert "root_path" not in status.text
    assert "content" not in status.json()["result"]

    restore_headers = {
        "Authorization": f"Bearer {external_token}",
        "Idempotency-Key": "e2e-file-restore-1",
    }
    restore_proposal = client.post(
        "/api/v1/actions",
        headers=restore_headers,
        json={
            "action": "file.restore.v1",
            "workspace_id": workspace_id,
            "quarantine_entry_id": action_id,
        },
    )
    assert restore_proposal.status_code == 200
    restore_action_id = restore_proposal.json()["id"]
    approval_csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    restore_approved = client.post(
        f"/api/approvals/{restore_action_id}/approve",
        json={"note": "确认恢复原路径"},
        headers={"Origin": "http://localhost:5173", "X-CSRF-Token": approval_csrf},
    )
    assert restore_approved.status_code == 200

    restore_claim = client.post(
        "/api/v1/worker/claim",
        headers=worker_headers,
        json={
            "protocol_version": "1.0",
            "capabilities": ["file.quarantine.v1", "file.restore.v1"],
        },
    )
    assert restore_claim.status_code == 200
    restore_grant = restore_claim.json()
    restore_task_id = UUID(restore_grant["task_id"])
    restore_started = client.post(
        f"/api/v1/worker/tasks/{restore_task_id}/start",
        headers=worker_headers,
        json={
            "protocol_version": "1.0",
            "request_digest": restore_grant["request_digest"],
        },
    )
    assert restore_started.status_code == 204
    entry_context = client.get(
        f"/api/v1/worker/quarantine-entries/{action_id}",
        params={"version": 1, "task_id": str(restore_task_id)},
        headers=worker_headers,
    )
    assert entry_context.status_code == 200
    assert "quarantine_absolute_path" not in entry_context.json()
    restore_completed = client.post(
        f"/api/v1/worker/tasks/{restore_task_id}/complete",
        headers=worker_headers,
        json={
            "protocol_version": "1.0",
            "request_digest": restore_grant["request_digest"],
            "result": {
                "status": "succeeded",
                "result_kind": "file_restore",
                "side_effect": "restored",
                "content_sha256": digest,
                "size_bytes": 4,
            },
        },
    )
    assert restore_completed.status_code == 200
    restore_status = client.get(
        f"/api/v1/actions/{restore_action_id}", headers=restore_headers
    )
    assert restore_status.status_code == 200
    assert restore_status.json()["status"] == "succeeded"
    assert restore_status.json()["result"]["side_effect"] == "restored"
