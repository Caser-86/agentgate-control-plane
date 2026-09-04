from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.auth.models import ClientToken
from app.auth.security import digest_secret
from app.control.enums import SideEffectCertainty, TaskKind
from app.control.repositories import enqueue_task
from app.files.models import ManagedWorkspace
from tests.conftest import authenticate_client


def _register_file_worker(client: TestClient, engine: Engine) -> dict[str, object]:
    enrollment = f"worker-enrollment-{uuid4()}"
    with Session(engine) as session:
        session.add(
            ClientToken(
                name="file-worker-enrollment",
                token_digest=digest_secret(enrollment),
                scopes=["worker:enroll"],
            )
        )
        session.commit()
    response = client.post(
        "/api/v1/worker/register",
        headers={"Authorization": f"Bearer {enrollment}"},
        json={
            "name": "file-worker",
            "version": "0.1.0",
            "protocol_version": "1.0",
            "capabilities": ["file.inspect.v1"],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_worker_context_requires_active_grant_and_matching_version(
    auth_client: tuple[TestClient, Engine, Path], tmp_path: Path
) -> None:
    client, engine, token_file = auth_client
    authenticate_client(client, token_file)
    root = tmp_path / "project"
    root.mkdir()
    workspace = ManagedWorkspace(
        name="Worker 工作区",
        root_path=str(root),
        canonical_root_path=str(root),
        quarantine_root_path=str(tmp_path / "quarantine"),
        protected_patterns=[".env"],
        enabled=True,
        version=1,
    )
    with Session(engine) as session:
        session.add(workspace)
        session.flush()
        workspace_id = workspace.id
        task = enqueue_task(
            session,
            kind=TaskKind.CONTROL,
            capability="file.inspect.v1",
            payload={
                "workspace_id": str(workspace.id),
                "workspace_version": 1,
                "relative_path": "notes.txt",
                "arguments_digest": "a" * 64,
                "policy_version": "file-policy.v1",
            },
            idempotency_key="worker-context-task",
            side_effect_certainty=SideEffectCertainty.READ_ONLY,
        )
        session.commit()
        task_id = task.id
    identity = _register_file_worker(client, engine)
    worker_headers = {"Authorization": f"Bearer {identity['token']}"}
    claim = client.post(
        "/api/v1/worker/claim",
        headers=worker_headers,
        json={"protocol_version": "1.0", "capabilities": ["file.inspect.v1"]},
    ).json()
    assert UUID(claim["task_id"]) == task_id
    started = client.post(
        f"/api/v1/worker/tasks/{task_id}/start",
        headers=worker_headers,
        json={"protocol_version": "1.0", "request_digest": claim["request_digest"]},
    )
    assert started.status_code == 204

    response = client.get(
        f"/api/v1/worker/workspaces/{workspace_id}",
        params={"version": 1, "task_id": str(task_id)},
        headers=worker_headers,
    )
    assert response.status_code == 200
    assert response.json()["root_path"] == str(root)
    assert response.json()["version"] == 1

    stale = client.get(
        f"/api/v1/worker/workspaces/{workspace_id}",
        params={"version": 2, "task_id": str(task_id)},
        headers=worker_headers,
    )
    assert stale.status_code == 409
