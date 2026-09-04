from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from agentgate_worker.client import (
    TaskGrant,
    WorkerClient,
    WorkerProtocolError,
    WorkspaceContext,
    _safe_task_payload,
)
from agentgate_worker.journal import WorkerJournal
from agentgate_worker.quarantine import QuarantineEntryView
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
            "action_id": str(uuid4()),
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
                "action_id": str(uuid4()),
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


def test_file_inspect_result_contains_metadata_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "notes.txt").write_bytes(b"hello")
    context = WorkspaceContext(
        workspace_id=str(WORKSPACE_ID),
        version=2,
        root_path=str(root),
        quarantine_root_path=str(tmp_path / "quarantine"),
        protected_patterns=(".env",),
    )
    client = WorkerClient(
        base_url="http://127.0.0.1:8000",
        vault=InMemoryVault(),
        journal=WorkerJournal(tmp_path / "journal.db"),
        worker_name="local-worker",
        worker_version="0.1.0",
        capabilities={"file.inspect.v1"},
    )
    grant = _grant()
    grant = TaskGrant(
        task_id=grant.task_id,
        idempotency_key=grant.idempotency_key,
        request_digest=grant.request_digest,
        lease_expires_at=grant.lease_expires_at,
        payload=grant.payload,
        capability="file.inspect.v1",
    )
    monkeypatch.setattr(client, "get_workspace_context", lambda _grant: context)

    result = client.file_result(grant)

    assert result == {
        "status": "succeeded",
        "result_kind": "file_metadata",
        "side_effect": "none",
        "content_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        "size_bytes": 5,
    }


def test_file_quarantine_result_moves_real_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    quarantine = tmp_path / "quarantine"
    root.mkdir()
    quarantine.mkdir()
    (root / "report.txt").write_bytes(b"stable")
    context = WorkspaceContext(
        workspace_id=str(WORKSPACE_ID),
        version=2,
        root_path=str(root),
        quarantine_root_path=str(quarantine),
        protected_patterns=(".env",),
    )
    client = WorkerClient(
        base_url="http://127.0.0.1:8000",
        vault=InMemoryVault(),
        journal=WorkerJournal(tmp_path / "journal.db"),
        worker_name="local-worker",
        worker_version="0.1.0",
        capabilities={"file.quarantine.v1"},
    )
    base = _grant()
    grant = TaskGrant(
        task_id=base.task_id,
        idempotency_key=base.idempotency_key,
        request_digest=base.request_digest,
        lease_expires_at=base.lease_expires_at,
        payload={
            **base.payload,
            "relative_path": "report.txt",
            "reason": "演示隔离",
        },
        capability="file.quarantine.v1",
    )
    monkeypatch.setattr(client, "get_workspace_context", lambda _grant: context)

    result = client.file_result(grant)

    assert result["status"] == "succeeded"
    assert result["result_kind"] == "file_quarantine"
    assert result["side_effect"] == "quarantined"
    assert result["size_bytes"] == 6
    assert not (root / "report.txt").exists()


def test_file_restore_result_moves_entry_back_without_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    quarantine = tmp_path / "quarantine"
    root.mkdir()
    quarantine_entry = quarantine / "entries" / "restore-entry" / "report.txt"
    quarantine_entry.parent.mkdir(parents=True)
    quarantine_entry.write_bytes(b"restore-me")
    entry_id = uuid4()
    action_id = uuid4()
    import hashlib

    digest = hashlib.sha256(b"restore-me").hexdigest()
    context = WorkspaceContext(
        workspace_id=str(WORKSPACE_ID),
        version=2,
        root_path=str(root),
        quarantine_root_path=str(quarantine),
        protected_patterns=(".env",),
    )
    entry = QuarantineEntryView(
        id=entry_id,
        workspace_id=str(WORKSPACE_ID),
        action_id=action_id,
        original_relative_path="report.txt",
        quarantine_relative_path="entries/restore-entry/report.txt",
        quarantine_absolute_path=str(quarantine_entry),
        content_sha256=digest,
        size_bytes=10,
        status="quarantined",
    )
    client = WorkerClient(
        base_url="http://127.0.0.1:8000",
        vault=InMemoryVault(),
        journal=WorkerJournal(tmp_path / "journal.db"),
        worker_name="local-worker",
        worker_version="0.1.0",
        capabilities={"file.restore.v1"},
    )
    base = _grant()
    grant = TaskGrant(
        task_id=base.task_id,
        idempotency_key=base.idempotency_key,
        request_digest=base.request_digest,
        lease_expires_at=base.lease_expires_at,
        payload={
            "action_id": str(action_id),
            "workspace_id": str(WORKSPACE_ID),
            "workspace_version": 2,
            "quarantine_entry_id": str(entry_id),
            "arguments_digest": "b" * 64,
            "policy_version": "file-policy.v1",
        },
        capability="file.restore.v1",
    )
    monkeypatch.setattr(client, "get_workspace_context", lambda _grant: context)
    monkeypatch.setattr(client, "get_quarantine_entry", lambda _grant, _context: entry)

    result = client.file_result(grant)

    assert result == {
        "status": "succeeded",
        "result_kind": "file_restore",
        "side_effect": "restored",
        "content_sha256": digest,
        "size_bytes": 10,
    }
    assert (root / "report.txt").read_bytes() == b"restore-me"


def test_client_recovers_file_result_without_dropping_side_effect_fields(tmp_path: Path) -> None:
    journal = WorkerJournal(tmp_path / "journal.db")
    journal.record_started("file-task-1", "c" * 64, datetime.now(UTC) + timedelta(seconds=30))
    journal.record_result(
        "file-task-1",
        {
            "status": "succeeded",
            "result_kind": "file_quarantine",
            "side_effect": "quarantined",
            "content_sha256": "a" * 64,
            "size_bytes": 12,
            "quarantine_entry_id": str(uuid4()),
            "quarantine_relative_path": "entries/demo/file.txt",
        },
    )
    transport = ContextTransport()
    client = WorkerClient(
        base_url="http://localhost:8000",
        vault=InMemoryVault(),
        journal=journal,
        transport=transport,
        worker_name="local-worker",
        worker_version="0.1.0",
        capabilities={"file.quarantine.v1"},
    )
    client.vault.save(WorkerCredentials("worker-1", "worker-token", "1.0"))

    assert client.recover_pending_reports() == 1
    assert transport.requests[-1][2]["result"]["side_effect"] == "quarantined"
