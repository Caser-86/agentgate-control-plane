from datetime import UTC, datetime, timedelta

import pytest

from agentgate_worker.client import HttpTransport, WorkerClient
from agentgate_worker.journal import WorkerJournal
from agentgate_worker.vault import WorkerCredentials


class InMemoryVault:
    def __init__(self) -> None:
        self.credentials: WorkerCredentials | None = None

    def save(self, credentials: WorkerCredentials) -> None:
        self.credentials = credentials

    def load(self) -> WorkerCredentials | None:
        return self.credentials


class RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    def request(
        self, method: str, path: str, *, headers: dict[str, str], json: dict[str, object]
    ) -> dict[str, object]:
        self.requests.append((method, path, json))
        if path == "/api/v1/worker/register":
            return {"worker_id": "worker-1", "token": "worker-token", "protocol_version": "1.0"}
        return {"status": "succeeded"}


def test_client_recovers_journaled_result_using_report_endpoint(tmp_path: object) -> None:
    """Replacing recovery with complete would make a post-disconnect retry non-idempotent."""
    journal = WorkerJournal(tmp_path / "journal.db")  # type: ignore[operator]
    journal.record_started("task-1", "c" * 64, datetime.now(UTC) + timedelta(seconds=30))
    journal.record_result("task-1", {"status": "succeeded"})
    transport = RecordingTransport()
    client = WorkerClient(
        base_url="http://localhost:8000",
        vault=InMemoryVault(),
        journal=journal,
        transport=transport,
        worker_name="local-worker",
        worker_version="0.1.0",
        capabilities={"platform.self_check"},
    )
    client.vault.save(WorkerCredentials("worker-1", "worker-token", "1.0"))

    recovered = client.recover_pending_reports()

    assert recovered == 1
    assert transport.requests[-1][1] == "/api/v1/worker/tasks/task-1/report"
    assert journal.pending_reports() == []


def test_client_complete_sends_only_self_check_fields(tmp_path: object) -> None:
    journal = WorkerJournal(tmp_path / "journal.db")  # type: ignore[operator]
    journal.record_started("task-2", "a" * 64, datetime.now(UTC) + timedelta(seconds=30))
    transport = RecordingTransport()
    client = WorkerClient(
        base_url="http://localhost:8000",
        vault=InMemoryVault(),
        journal=journal,
        transport=transport,
        worker_name="local-worker",
        worker_version="0.1.0",
        capabilities={"platform.self_check"},
    )
    client.vault.save(WorkerCredentials("worker-1", "worker-token", "1.0"))
    grant = type("Grant", (), {"task_id": "task-2", "request_digest": "a" * 64})()

    client.complete(
        grant,
        {
            "status": "succeeded",
            "detail": "read-only",
            "command": "powershell Remove-Item C:\\",
            "unknown": {"client_secret": "not-for-journal"},
        },
    )

    sent = transport.requests[-1][2]["result"]
    assert sent == {"status": "succeeded", "detail": "read-only"}


@pytest.mark.parametrize(
    "base_url",
    [
        "http://example.com:8000",
        "http://192.0.2.10:8000",
        "http://127.0.0.1.evil.example:8000",
        "ftp://127.0.0.1:8000",
        "http://[::1:8000",
        "http://127.0.0.1:not-a-port",
    ],
)
def test_http_transport_rejects_unsafe_api_url_before_request(base_url: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        HttpTransport(base_url)


@pytest.mark.parametrize(
    "base_url", ["http://localhost:8000", "https://127.0.0.1:8443", "http://[::1]:8000"]
)
def test_worker_client_accepts_documented_loopback_api_url(
    base_url: str, tmp_path: object
) -> None:
    client = WorkerClient(
        base_url=base_url,
        vault=InMemoryVault(),
        journal=WorkerJournal(tmp_path / "journal.db"),  # type: ignore[operator]
        worker_name="local-worker",
        worker_version="0.1.0",
        capabilities={"platform.self_check"},
    )
    assert isinstance(client.transport, HttpTransport)


def test_worker_client_rejects_unsafe_api_url_even_with_custom_transport(
    tmp_path: object,
) -> None:
    with pytest.raises(ValueError, match="loopback"):
        WorkerClient(
            base_url="http://example.com:8000",
            vault=InMemoryVault(),
            journal=WorkerJournal(tmp_path / "journal.db"),  # type: ignore[operator]
            worker_name="local-worker",
            worker_version="0.1.0",
            capabilities={"platform.self_check"},
            transport=RecordingTransport(),
        )
