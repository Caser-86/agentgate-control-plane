import ipaddress
import ntpath
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from agentgate_worker.journal import WorkerJournal
from agentgate_worker.probes import (
    probe_http,
    probe_windows_service,
    validate_http_target,
    validate_windows_service_name,
)
from agentgate_worker.vault import WorkerCredentials, WorkerVault

if TYPE_CHECKING:
    from agentgate_worker.quarantine import QuarantineEntryView

PROTOCOL_VERSION = "1.0"
SELF_CHECK_CAPABILITY = "platform.self_check"
HTTP_MONITOR_CAPABILITY = "monitor.http"
WINDOWS_SERVICE_MONITOR_CAPABILITY = "monitor.windows_service"
FILE_CAPABILITIES = frozenset(
    {"file.inspect.v1", "file.quarantine.v1", "file.restore.v1"}
)
SUPPORTED_CAPABILITIES = frozenset(
    {SELF_CHECK_CAPABILITY, HTTP_MONITOR_CAPABILITY, WINDOWS_SERVICE_MONITOR_CAPABILITY}
    | FILE_CAPABILITIES
)
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


def sanitize_monitor_result(result: dict[str, object]) -> dict[str, object]:
    if not isinstance(result, dict):
        raise WorkerProtocolError("Worker probe result must be an object")
    status = result.get("status")
    if status not in {"healthy", "failed", "unknown"}:
        raise WorkerProtocolError("Worker probe result has an unsupported status")
    safe: dict[str, object] = {"status": status}
    detail = result.get("detail")
    if isinstance(detail, str):
        safe["detail"] = detail[:512]
    latency_ms = result.get("latency_ms")
    if (
        isinstance(latency_ms, int)
        and not isinstance(latency_ms, bool)
        and 0 <= latency_ms <= 60_000
    ):
        safe["latency_ms"] = latency_ms
    return safe


def sanitize_file_result(result: dict[str, object]) -> dict[str, object]:
    if not isinstance(result, dict):
        raise WorkerProtocolError("Worker file result must be an object")
    status = result.get("status")
    if status not in {"succeeded", "failed"}:
        raise WorkerProtocolError("Worker file result has an unsupported status")
    result_kind = result.get("result_kind")
    side_effect = result.get("side_effect")
    if result_kind not in {"file_metadata", "file_quarantine", "file_restore"}:
        raise WorkerProtocolError("Worker file result has an unsupported result kind")
    if side_effect not in {"none", "quarantined", "restored", "conflict"}:
        raise WorkerProtocolError("Worker file result has an unsupported side effect")
    safe: dict[str, object] = {
        "status": status,
        "result_kind": result_kind,
        "side_effect": side_effect,
    }
    digest = result.get("content_sha256")
    if digest is not None:
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise WorkerProtocolError("Worker file result has an invalid digest")
        safe["content_sha256"] = digest
    elif status == "succeeded":
        raise WorkerProtocolError("Worker file result is missing digest")
    size_bytes = result.get("size_bytes")
    if size_bytes is not None:
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise WorkerProtocolError("Worker file result has an invalid size")
        safe["size_bytes"] = size_bytes
    elif status == "succeeded":
        raise WorkerProtocolError("Worker file result is missing size")
    for key in ("error_code", "error_message"):
        value = result.get(key)
        if isinstance(value, str):
            safe[key] = value[:256]
    entry_id = result.get("quarantine_entry_id")
    if entry_id is not None:
        try:
            safe["quarantine_entry_id"] = str(UUID(str(entry_id)))
        except (TypeError, ValueError) as error:
            raise WorkerProtocolError("Worker file result has an invalid entry ID") from error
    relative = result.get("quarantine_relative_path")
    if relative is not None:
        safe["quarantine_relative_path"] = _safe_file_relative_path(relative)
    return safe


def _safe_file_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise WorkerProtocolError("Worker received an unsafe file path")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or ntpath.splitdrive(normalized)[0]:
        raise WorkerProtocolError("Worker received an unsafe file path")
    segments = normalized.split("/")
    if any(not segment or segment in {".", ".."} or ":" in segment for segment in segments):
        raise WorkerProtocolError("Worker received an unsafe file path")
    return normalized


def _safe_task_payload(payload: object, capability: str | None = None) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise WorkerProtocolError("Worker received an unsafe task payload")
    if capability in FILE_CAPABILITIES:
        expected = {
            "file.inspect.v1": {
                "action_id",
                "workspace_id",
                "workspace_version",
                "relative_path",
                "arguments_digest",
                "policy_version",
            },
            "file.quarantine.v1": {
                "action_id",
                "workspace_id",
                "workspace_version",
                "relative_path",
                "arguments_digest",
                "policy_version", "reason",
            },
            "file.restore.v1": {
                "action_id",
                "workspace_id",
                "workspace_version",
                "quarantine_entry_id",
                "arguments_digest",
                "policy_version",
            },
        }[capability]
        if set(payload) != expected:
            raise WorkerProtocolError("Worker received an unsafe file task payload")
        try:
            UUID(str(payload["workspace_id"]))
            UUID(str(payload["action_id"]))
            if (
                not isinstance(payload["workspace_version"], int)
                or payload["workspace_version"] <= 0
            ):
                raise ValueError
            if not isinstance(payload["arguments_digest"], str) or not re.fullmatch(
                r"[0-9a-f]{64}", payload["arguments_digest"]
            ):
                raise ValueError
            if payload["policy_version"] != "file-policy.v1":
                raise ValueError
            if "relative_path" in payload:
                _safe_file_relative_path(payload["relative_path"])
            if "quarantine_entry_id" in payload:
                UUID(str(payload["quarantine_entry_id"]))
            if "reason" in payload and (
                not isinstance(payload["reason"], str)
                or not 1 <= len(payload["reason"]) <= 500
            ):
                raise ValueError
        except (TypeError, ValueError) as error:
            raise WorkerProtocolError("Worker received an unsafe file task payload") from error
        return payload
    task_type = payload.get("task_type")
    if task_type == SELF_CHECK_CAPABILITY:
        if payload != {"task_type": SELF_CHECK_CAPABILITY}:
            raise WorkerProtocolError("Worker received an unsafe task payload")
        return payload
    expected = {"task_type", "target_id", "endpoint", "timeout_seconds"}
    if task_type not in {HTTP_MONITOR_CAPABILITY, WINDOWS_SERVICE_MONITOR_CAPABILITY}:
        raise WorkerProtocolError("Worker received an unsupported task payload")
    if set(payload) != expected or not isinstance(payload.get("target_id"), str):
        raise WorkerProtocolError("Worker received an unsafe task payload")
    try:
        UUID(payload["target_id"])
        timeout_seconds = payload["timeout_seconds"]
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= 30
        ):
            raise ValueError
        if task_type == HTTP_MONITOR_CAPABILITY:
            validate_http_target(str(payload["endpoint"]))
        else:
            validate_windows_service_name(str(payload["endpoint"]))
    except (TypeError, ValueError) as error:
        raise WorkerProtocolError("Worker received an unsafe task payload") from error
    return payload


def sanitize_result_for_grant(grant: "TaskGrant", result: dict[str, object]) -> dict[str, object]:
    if getattr(grant, "capability", "") in FILE_CAPABILITIES:
        return sanitize_file_result(result)
    payload = getattr(grant, "payload", {"task_type": SELF_CHECK_CAPABILITY})
    if payload.get("task_type") == SELF_CHECK_CAPABILITY:
        return sanitize_self_check_result(result)
    return sanitize_monitor_result(result)


class Transport(Protocol):
    def request(
        self, method: str, path: str, *, headers: dict[str, str], json: dict[str, object]
    ) -> dict[str, object] | None: ...


class HttpTransport:
    def __init__(self, base_url: str) -> None:
        self.base_url = validate_api_url(base_url)

    def request(
        self, method: str, path: str, *, headers: dict[str, str], json: dict[str, object]
    ) -> dict[str, object] | None:
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
        if payload is None:
            return None
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
    capability: str = ""


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: str
    version: int
    root_path: str
    quarantine_root_path: str
    protected_patterns: tuple[str, ...]


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
        if not capabilities or not capabilities <= SUPPORTED_CAPABILITIES:
            raise ValueError("Worker capabilities contain an unsupported capability")
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
        if not isinstance(response, dict):
            raise WorkerProtocolError("Worker registration response was malformed")
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

    def _request(
        self, method: str, path: str, payload: dict[str, object]
    ) -> dict[str, object] | None:
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
            raw_payload = response["payload"]
            raw_capability = response.get("capability")
            if raw_capability is None and isinstance(raw_payload, dict):
                raw_capability = raw_payload.get("task_type")
            capability = str(raw_capability or "")
            payload = _safe_task_payload(raw_payload, capability)
            lease = datetime.fromisoformat(str(response["lease_expires_at"]))
            if lease.tzinfo is None:
                lease = lease.replace(tzinfo=UTC)
            return TaskGrant(
                task_id=str(response["task_id"]),
                idempotency_key=str(response["idempotency_key"]),
                request_digest=str(response["request_digest"]),
                lease_expires_at=lease,
                payload=payload,
                capability=capability,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WorkerProtocolError("Worker claim response was malformed") from error

    def get_workspace_context(self, grant: TaskGrant) -> WorkspaceContext:
        workspace_id = grant.payload.get("workspace_id")
        version = grant.payload.get("workspace_version")
        if not isinstance(workspace_id, str) or not isinstance(version, int):
            raise WorkerProtocolError("Worker received an unsafe file task payload")
        response = self._request(
            "GET",
            f"/api/v1/worker/workspaces/{workspace_id}?version={version}&task_id={grant.task_id}",
            {},
        )
        if not isinstance(response, dict):
            raise WorkerProtocolError("Worker workspace context was malformed")
        try:
            response_version = response["version"]
            if (
                str(response["workspace_id"]) != workspace_id
                or not isinstance(response_version, int)
                or response_version != version
            ):
                raise ValueError
            root_path = response["root_path"]
            quarantine_root_path = response["quarantine_root_path"]
            patterns = response["protected_patterns"]
            if (
                not isinstance(root_path, str)
                or not isinstance(quarantine_root_path, str)
                or not isinstance(patterns, list)
                or not all(isinstance(item, str) for item in patterns)
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise WorkerProtocolError("Worker workspace context was malformed") from error
        return WorkspaceContext(
            workspace_id=workspace_id,
            version=version,
            root_path=root_path,
            quarantine_root_path=quarantine_root_path,
            protected_patterns=tuple(patterns),
        )

    def get_quarantine_entry(
        self, grant: TaskGrant, context: WorkspaceContext
    ) -> "QuarantineEntryView":
        from agentgate_worker.quarantine import QuarantineEntryView

        entry_id = grant.payload.get("quarantine_entry_id")
        if not isinstance(entry_id, str):
            raise WorkerProtocolError("Worker received an unsafe quarantine entry ID")
        response = self._request(
            "GET",
            f"/api/v1/worker/quarantine-entries/{entry_id}"
            f"?version={context.version}&task_id={grant.task_id}",
            {},
        )
        if not isinstance(response, dict):
            raise WorkerProtocolError("Worker quarantine entry was malformed")
        try:
            returned_id = UUID(str(response["id"]))
            action_id = UUID(str(response["action_id"]))
            workspace_id = str(response["workspace_id"])
            version = response["workspace_version"]
            original_relative_path = _safe_file_relative_path(
                response["original_relative_path"]
            )
            quarantine_relative_path = _safe_file_relative_path(
                response["quarantine_relative_path"]
            )
            content_sha256 = str(response["content_sha256"])
            size_bytes = response["size_bytes"]
            status = str(response["status"])
            if (
                returned_id != UUID(entry_id)
                or workspace_id != context.workspace_id
                or not isinstance(version, int)
                or version != context.version
                or not re.fullmatch(r"[0-9a-f]{64}", content_sha256)
                or not isinstance(size_bytes, int)
                or isinstance(size_bytes, bool)
                or size_bytes < 0
                or status not in {"quarantined", "restored"}
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise WorkerProtocolError("Worker quarantine entry was malformed") from error
        quarantine_absolute_path = Path(context.quarantine_root_path).joinpath(
            *quarantine_relative_path.split("/")
        )
        return QuarantineEntryView(
            id=returned_id,
            workspace_id=workspace_id,
            action_id=action_id,
            original_relative_path=original_relative_path,
            quarantine_relative_path=quarantine_relative_path,
            quarantine_absolute_path=str(quarantine_absolute_path),
            content_sha256=content_sha256,
            size_bytes=size_bytes,
            status=status,
        )

    def start(self, grant: TaskGrant) -> None:
        self._request(
            "POST",
            f"/api/v1/worker/tasks/{grant.task_id}/start",
            {"request_digest": grant.request_digest},
        )
        self.journal.record_started(grant.task_id, grant.request_digest, grant.lease_expires_at)

    def complete(self, grant: TaskGrant, result: dict[str, object]) -> None:
        safe_result = sanitize_result_for_grant(grant, result)
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
            if result.get("result_kind") in {
                "file_metadata",
                "file_quarantine",
                "file_restore",
            }:
                safe_result = sanitize_file_result(result)
            elif result.get("status") in {"healthy", "failed", "unknown"}:
                safe_result = sanitize_monitor_result(result)
            else:
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

    def probe_result(self, grant: TaskGrant) -> dict[str, object]:
        task_type = grant.payload.get("task_type")
        endpoint = grant.payload.get("endpoint")
        timeout_seconds = grant.payload.get("timeout_seconds")
        if not isinstance(endpoint, str) or not isinstance(timeout_seconds, int):
            raise WorkerProtocolError("Worker received an unsafe task payload")
        if task_type == HTTP_MONITOR_CAPABILITY:
            return probe_http(endpoint, timeout_seconds=timeout_seconds)
        if task_type == WINDOWS_SERVICE_MONITOR_CAPABILITY:
            return probe_windows_service(endpoint)
        if task_type == SELF_CHECK_CAPABILITY:
            return self.self_check_result()
        raise WorkerProtocolError("Worker received an unsupported task payload")

    def file_result(self, grant: TaskGrant) -> dict[str, object]:
        from agentgate_worker.filesystem import FileActionError, FileConnector
        from agentgate_worker.quarantine import QuarantineService

        capability = grant.capability
        if capability not in FILE_CAPABILITIES:
            raise WorkerProtocolError("Worker received an unsupported file task")
        context = self.get_workspace_context(grant)
        try:
            if capability == "file.inspect.v1":
                relative_path = grant.payload["relative_path"]
                metadata = FileConnector().inspect(context, str(relative_path))
                return {
                    "status": "succeeded",
                    "result_kind": "file_metadata",
                    "side_effect": "none",
                    "content_sha256": metadata.content_sha256,
                    "size_bytes": metadata.size_bytes,
                }
            service = QuarantineService(self.journal.path.with_name("file-actions.jsonl"))
            if capability == "file.quarantine.v1":
                quarantine_result = service.quarantine(
                    context,
                    UUID(str(grant.payload["action_id"])),
                    str(grant.payload["relative_path"]),
                )
                return {
                    "status": "succeeded",
                    "result_kind": "file_quarantine",
                    "side_effect": "quarantined",
                    "content_sha256": quarantine_result.content_sha256,
                    "size_bytes": quarantine_result.size_bytes,
                    "quarantine_entry_id": str(quarantine_result.entry.id),
                    "quarantine_relative_path": quarantine_result.entry.quarantine_relative_path,
                }
            entry = self.get_quarantine_entry(grant, context)
            result = service.restore(context, entry)
            if result.status == "destination_conflict":
                return {
                    "status": "failed",
                    "result_kind": "file_restore",
                    "side_effect": "conflict",
                    "content_sha256": result.content_sha256,
                    "size_bytes": result.size_bytes,
                    "error_code": "destination_conflict",
                    "error_message": "恢复目标已存在，未覆盖",
                }
            return {
                "status": "succeeded",
                "result_kind": "file_restore",
                "side_effect": "restored",
                "content_sha256": result.content_sha256,
                "size_bytes": result.size_bytes,
            }
        except FileActionError as error:
            result_kind = (
                "file_metadata"
                if capability == "file.inspect.v1"
                else "file_quarantine"
            )
            return {
                "status": "failed",
                "result_kind": result_kind,
                "side_effect": "none",
                "error_code": error.code,
                "error_message": error.message,
            }
