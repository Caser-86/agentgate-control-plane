import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from agentgate_worker.journal import WorkerJournal
from agentgate_worker.vault import WorkerCredentials, WorkerVault

PROTOCOL_VERSION = "1.0"
SELF_CHECK_CAPABILITY = "platform.self_check"
SELF_CHECK_RESULT_KEYS = frozenset(
    {"status", "detail", "worker_version", "protocol_version", "capabilities"}
)


class WorkerProtocolError(RuntimeError):
    pass


def validate_api_url(base_url: str) -> str:
    """Validate and normalize the Worker API origin before any credential use."""
    try:
        parsed = urlsplit(base_url)
        hostname = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise ValueError("Worker API URL must be a valid loopback HTTP(S) URL") from error
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Worker API URL must be a valid loopback HTTP(S) URL")
    normalized_host = hostname.lower().rstrip(".")
    is_loopback = normalized_host == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(normalized_host).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise ValueError("Worker API URL must target a loopback host")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Worker API URL port must be between 1 and 65535")
    return base_url.rstrip("/")


def sanitize_self_check_result(result: dict[str, object]) -> dict[str, object]:
    if not isinstance(result, dict):
        raise WorkerProtocolError("Worker self-check result must be an object")
    safe: dict[str, object] = {}
    for key in SELF_CHECK_RESULT_KEYS - {"capabilities"}:
        value = result.get(key)
        if isinstance(value, str):
            safe[key] = value
    capabilities = result.get("capabilities")
    if isinstance(capabilities, list) and all(isinstance(item, str) for item in capabilities):
        safe["capabilities"] = sorted(set(capabilities))
    if "status" not in safe:
        raise WorkerProtocolError("Worker self-check result is missing status")
    return safe


class Transport(Protocol):
    def request(
        self, method: str, path: str, *, headers: dict[str, str], json: dict[str, object]
    ) -> dict[str, object]: ...


class HttpTransport:
    def __init__(self, base_url: str) -> None:
        self.base_url = validate_api_url(base_url)

    def request(
        self, method: str, path: str, *, headers: dict[str, str], json: dict[str, object]
    ) -> dict[str, object]:
        try:
            response = httpx.request(
                method, f"{self.base_url}{path}", headers=headers, json=json, timeout=10.0
            )
            if response.status_code >= 400:
                raise WorkerProtocolError(f"Worker API request rejected: {response.status_code}")
            if response.status_code == 204:
                return {}
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise WorkerProtocolError("Worker API request unavailable") from error
        if not isinstance(payload, dict):
            raise WorkerProtocolError("Worker API returned malformed payload")
        return payload


@dataclass(frozen=True)
class WorkerIdentity:
    worker_id: str
    protocol_version: str
    lease_seconds: int
    max_journal_result_bytes: int


@dataclass(frozen=True)
class TaskGrant:
    task_id: str
    idempotency_key: str
    request_digest: str
    lease_expires_at: datetime
    payload: dict[str, object]


class WorkerClient:
    def __init__(
        self,
        *,
        base_url: str,
        vault: WorkerVault,
        journal: WorkerJournal,
        worker_name: str,
        worker_version: str,
        capabilities: set[str],
        transport: Transport | None = None,
    ) -> None:
        if capabilities != {SELF_CHECK_CAPABILITY}:
            raise ValueError("Phase 0 Worker only supports platform.self_check")
        validated_base_url = validate_api_url(base_url)
        self.vault = vault
        self.journal = journal
        self.worker_name = worker_name
        self.worker_version = worker_version
        self.capabilities = capabilities
        self.transport = transport or HttpTransport(validated_base_url)

    def register(self, enrollment_token: str) -> WorkerIdentity:
        response = self.transport.request(
            "POST",
            "/api/v1/worker/register",
            headers={"Authorization": f"Bearer {enrollment_token}"},
            json={
                "name": self.worker_name,
                "version": self.worker_version,
                "protocol_version": PROTOCOL_VERSION,
                "capabilities": sorted(self.capabilities),
            },
        )
        try:
            credentials = WorkerCredentials(
                worker_id=str(response["worker_id"]),
                token=str(response["token"]),
                protocol_version=str(response["protocol_version"]),
            )
            lease_seconds = response["lease_seconds"]
            max_journal_result_bytes = response["max_journal_result_bytes"]
            if not isinstance(lease_seconds, int) or not isinstance(max_journal_result_bytes, int):
                raise WorkerProtocolError("Worker registration response was malformed")
            identity = WorkerIdentity(
                worker_id=credentials.worker_id,
                protocol_version=credentials.protocol_version,
                lease_seconds=lease_seconds,
                max_journal_result_bytes=max_journal_result_bytes,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WorkerProtocolError("Worker registration response was malformed") from error
        if identity.protocol_version != PROTOCOL_VERSION:
            raise WorkerProtocolError("Worker registration selected an unsupported protocol")
        self.vault.save(credentials)
        return identity

    def _credentials(self) -> WorkerCredentials:
        credentials = self.vault.load()
        if credentials is None or credentials.protocol_version != PROTOCOL_VERSION:
            raise WorkerProtocolError("Worker is not registered")
        return credentials

    def _request(self, method: str, path: str, payload: dict[str, object]) -> dict[str, object]:
        credentials = self._credentials()
        return self.transport.request(
            method,
            path,
            headers={"Authorization": f"Bearer {credentials.token}"},
            json={"protocol_version": credentials.protocol_version, **payload},
        )

    def heartbeat(self) -> None:
        self._request("POST", "/api/v1/worker/heartbeat", {})

    def claim(self) -> TaskGrant | None:
        response = self._request(
            "POST", "/api/v1/worker/claim", {"capabilities": sorted(self.capabilities)}
        )
        if not response:
            return None
        try:
            payload = response["payload"]
            if not isinstance(payload, dict) or payload != {"task_type": SELF_CHECK_CAPABILITY}:
                raise WorkerProtocolError("Worker received an unsafe task payload")
            lease = datetime.fromisoformat(str(response["lease_expires_at"]))
            if lease.tzinfo is None:
                lease = lease.replace(tzinfo=UTC)
            return TaskGrant(
                task_id=str(response["task_id"]),
                idempotency_key=str(response["idempotency_key"]),
                request_digest=str(response["request_digest"]),
                lease_expires_at=lease,
                payload=payload,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WorkerProtocolError("Worker claim response was malformed") from error

    def start(self, grant: TaskGrant) -> None:
        self._request(
            "POST",
            f"/api/v1/worker/tasks/{grant.task_id}/start",
            {"request_digest": grant.request_digest},
        )
        self.journal.record_started(grant.task_id, grant.request_digest, grant.lease_expires_at)

    def complete(self, grant: TaskGrant, result: dict[str, object]) -> None:
        safe_result = sanitize_self_check_result(result)
        self.journal.record_result(grant.task_id, safe_result)
        self._request(
            "POST",
            f"/api/v1/worker/tasks/{grant.task_id}/complete",
            {"request_digest": grant.request_digest, "result": safe_result},
        )
        self.journal.mark_reported(grant.task_id)

    def recover_pending_reports(self) -> int:
        recovered = 0
        for task_id, request_digest, result in self.journal.pending_reports():
            safe_result = sanitize_self_check_result(result)
            self._request(
                "POST",
                f"/api/v1/worker/tasks/{task_id}/report",
                {"request_digest": request_digest, "result": safe_result},
            )
            self.journal.mark_reported(task_id)
            recovered += 1
        return recovered

    def self_check_result(self) -> dict[str, object]:
        """Return static metadata without shell, service, filesystem, or network work."""
        return {
            "status": "succeeded",
            "worker_version": self.worker_version,
            "protocol_version": PROTOCOL_VERSION,
            "capabilities": sorted(self.capabilities),
        }
