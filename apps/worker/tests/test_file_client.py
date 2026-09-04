from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from agentgate_worker.client import TaskGrant, WorkerClient, WorkerProtocolError, _safe_task_payload
from agentgate_worker.journal import WorkerJournal
from agentgate_worker.vault import WorkerCredentials
from tests.test_client import InMemoryVault


class ContextTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    def request(
        self, method: str, path: str, *, headers: dict[str, str], json: dict[str, object]
    ) -> dict[str, object]:
        del headers
        self.requests.append((method, path, json))
        return {
            "workspace_id": str(WORKSPACE_ID),
            "version": 2,
            "root_path": r"C:\AgentGate\workspaces\demo",
            "quarantine_root_path": r"C:\AgentGate\.agentgate-quarantine\demo",
            "protected_patterns": [".env"],
        }


WORKSPACE_ID = uuid4()


def _grant() -> TaskGrant:
    return TaskGrant(
        task_id="task-file-context",
        idempotency_key="file-context",
        request_digest="a" * 64,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        payload={
            "workspace_id": str(WORKSPACE_ID),
            "workspace_version": 2,
            "relative_path": "notes.txt",
            "arguments_digest": "b" * 64,
            "policy_version": "file-policy.v1",
        },
    )


def test_file_task_payload_rejects_absolute_path() -> None:
    with pytest.raises(WorkerProtocolError):
        _safe_task_payload(
            {
                "workspace_id": str(WORKSPACE_ID),
                "workspace_version": 2,
                "relative_path": r"C:\secret.txt",
                "arguments_digest": "b" * 64,
                "policy_version": "file-policy.v1",
            },
            "file.inspect.v1",
        )


def test_client_fetches_context_for_claimed_file_task_without_sending_extra_root(
    tmp_path: object,
) -> None:
    transport = ContextTransport()
    client = WorkerClient(
        base_url="http://127.0.0.1:8000",
        vault=InMemoryVault(),
        journal=WorkerJournal(tmp_path / "journal.db"),  # type: ignore[operator]
        worker_name="local-worker",
        worker_version="0.1.0",
        capabilities={"file.inspect.v1"},
        transport=transport,
    )
    client.vault.save(WorkerCredentials("worker-1", "worker-token", "1.0"))

    context = client.get_workspace_context(_grant())

    assert context.version == 2
    assert context.root_path.endswith(r"workspaces\demo")
    assert "root_path" not in transport.requests[-1][2]
    assert "task-file-context" in transport.requests[-1][1]
