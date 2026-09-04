import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC
from typing import Annotated, Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import update
from sqlmodel import Session, select

from app.auth.models import ClientToken
from app.auth.security import digest_secret, new_secret
from app.control.enums import TaskKind, TaskOutcome, TaskStatus, WorkerStatus
from app.control.models import ControlTask, WorkerExecutionGrant, WorkerRegistration
from app.control.repositories import append_outbox_event, claim_next_task, complete_task
from app.models import utc_now
from app.monitoring.enums import (
    HTTP_MONITOR_CAPABILITY,
    WINDOWS_SERVICE_MONITOR_CAPABILITY,
    ProbeStatus,
)
from app.repositories import AuditRepository
from app.schemas_worker_files import (
    FileInspectTask,
    FileQuarantineTask,
    FileRestoreTask,
)
from app.services.audit import AuditService
from app.services.monitoring import validate_http_endpoint, validate_windows_service_name

PROTOCOL_VERSION = "1.0"
SELF_CHECK_CAPABILITY = "platform.self_check"
FILE_CAPABILITIES = frozenset(
    {"file.inspect.v1", "file.quarantine.v1", "file.restore.v1"}
)
SUPPORTED_CAPABILITIES = frozenset(
    {SELF_CHECK_CAPABILITY, HTTP_MONITOR_CAPABILITY, WINDOWS_SERVICE_MONITOR_CAPABILITY}
    | FILE_CAPABILITIES
)
MAX_RESULT_BYTES = 4096
MAX_CAPABILITIES = 6
SELF_CHECK_RESULT_KEYS = frozenset(
    {"status", "detail", "worker_version", "protocol_version", "capabilities"}
)


class WorkerProtocolError(ValueError):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


class _ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RegisterWorkerRequest(_ProtocolModel):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    version: Annotated[str, Field(min_length=1, max_length=64)]
    protocol_version: Annotated[str, Field(min_length=1, max_length=16)]
    capabilities: Annotated[list[str], Field(min_length=1, max_length=MAX_CAPABILITIES)]

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or not set(value) <= SUPPORTED_CAPABILITIES:
            raise ValueError("unsupported_worker_capability")
        return value


class ProtocolRequest(_ProtocolModel):
    protocol_version: Annotated[str, Field(min_length=1, max_length=16)]


class ClaimRequest(ProtocolRequest):
    capabilities: Annotated[list[str], Field(min_length=1, max_length=MAX_CAPABILITIES)]


class TaskMutationRequest(ProtocolRequest):
    request_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CompleteTaskRequest(TaskMutationRequest):
    result: dict[str, object]


@dataclass(frozen=True)
class RegisteredWorker:
    worker_id: UUID
    token: str
    protocol_version: str


def _audit(
    session: Session, *, event_type: str, worker_id: UUID, payload: dict[str, object]
) -> None:
    AuditService(AuditRepository(session)).append(
        event_type=event_type,
        actor=f"worker:{worker_id}",
        resource_type="worker",
        resource_id=worker_id,
        payload=payload,
        commit=False,
    )


def _require_protocol(received: str, expected: str) -> None:
    if received != expected or received != PROTOCOL_VERSION:
        raise WorkerProtocolError(403, "unsupported_protocol_version")


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as error:
        raise WorkerProtocolError(422, "invalid_json_value") from error


def request_digest(task: ControlTask) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "task_id": str(task.id),
                "idempotency_key": task.idempotency_key,
                "payload": task.payload,
            }
        )
    ).hexdigest()


def sanitize_self_check_result(result: dict[str, object]) -> dict[str, object]:
    if not isinstance(result, dict):
        raise WorkerProtocolError(422, "invalid_result")
    safe: dict[str, object] = {}
    for key in SELF_CHECK_RESULT_KEYS - {"capabilities"}:
        value = result.get(key)
        if isinstance(value, str):
            safe[key] = value
    capabilities = result.get("capabilities")
    if isinstance(capabilities, list) and all(isinstance(item, str) for item in capabilities):
        safe["capabilities"] = sorted(set(capabilities))
    if "status" not in safe:
        raise WorkerProtocolError(422, "invalid_result")
    encoded = _canonical_json(safe)
    if len(encoded) > MAX_RESULT_BYTES:
        raise WorkerProtocolError(422, "result_too_large")
    return safe


def sanitize_monitor_result(result: dict[str, object]) -> dict[str, object]:
    if not isinstance(result, dict):
        raise WorkerProtocolError(422, "invalid_result")
    status = result.get("status")
    if not isinstance(status, str) or status not in {item.value for item in ProbeStatus}:
        raise WorkerProtocolError(422, "invalid_result")
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
    encoded = _canonical_json(safe)
    if len(encoded) > MAX_RESULT_BYTES:
        raise WorkerProtocolError(422, "result_too_large")
    return safe


def sanitize_file_result(result: dict[str, object]) -> dict[str, object]:
    if not isinstance(result, dict):
        raise WorkerProtocolError(422, "invalid_result")
    status = result.get("status")
    if status not in {"succeeded", "failed"}:
        raise WorkerProtocolError(422, "invalid_result")
    result_kind = result.get("result_kind")
    side_effect = result.get("side_effect")
    digest = result.get("content_sha256")
    size_bytes = result.get("size_bytes")
    if not isinstance(result_kind, str) or result_kind not in {
        "file_metadata", "file_quarantine", "file_restore"
    }:
        raise WorkerProtocolError(422, "invalid_result")
    if not isinstance(side_effect, str) or side_effect not in {
        "none", "quarantined", "restored", "conflict"
    }:
        raise WorkerProtocolError(422, "invalid_result")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise WorkerProtocolError(422, "invalid_result")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
        raise WorkerProtocolError(422, "invalid_result")
    safe: dict[str, object] = {
        "status": status,
        "result_kind": result_kind,
        "side_effect": side_effect,
        "content_sha256": digest,
        "size_bytes": size_bytes,
    }
    for key in ("error_code", "error_message"):
        value = result.get(key)
        if isinstance(value, str):
            safe[key] = value[:256]
    if len(_canonical_json(safe)) > MAX_RESULT_BYTES:
        raise WorkerProtocolError(422, "result_too_large")
    return safe


def sanitize_result_for_task(task: ControlTask, result: dict[str, object]) -> dict[str, object]:
    if task.capability == SELF_CHECK_CAPABILITY:
        return sanitize_self_check_result(result)
    if task.capability in {
        HTTP_MONITOR_CAPABILITY,
        WINDOWS_SERVICE_MONITOR_CAPABILITY,
    }:
        return sanitize_monitor_result(result)
    if task.capability in FILE_CAPABILITIES:
        return sanitize_file_result(result)
    raise WorkerProtocolError(403, "unsupported_worker_capability")


def register_worker(
    session: Session, request: RegisterWorkerRequest, enrollment_token: str
) -> RegisteredWorker:
    _require_protocol(request.protocol_version, PROTOCOL_VERSION)
    try:
        enrollment = session.exec(
            select(ClientToken).where(
                ClientToken.token_digest == digest_secret(enrollment_token),
                cast(Any, ClientToken.revoked_at).is_(None),
            )
        ).first()
        if enrollment is None or "worker:enroll" not in enrollment.scopes:
            raise WorkerProtocolError(401, "invalid_enrollment_token")
        now = utc_now()
        if enrollment.expires_at is not None:
            expires_at = enrollment.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                raise WorkerProtocolError(401, "invalid_enrollment_token")
        consumed = session.exec(
            update(ClientToken)
            .where(
                cast(Any, ClientToken.id) == enrollment.id,
                cast(Any, ClientToken.revoked_at).is_(None),
                (
                    cast(Any, ClientToken.expires_at).is_(None)
                    | (cast(Any, ClientToken.expires_at) > now)
                ),
            )
            .values(revoked_at=now)
            .execution_options(synchronize_session=False)
        )
        if consumed.rowcount != 1:
            raise WorkerProtocolError(401, "invalid_enrollment_token")
        raw_worker_token = new_secret()
        worker = WorkerRegistration(
            name=request.name,
            version=request.version,
            protocol_version=request.protocol_version,
            capabilities=sorted(request.capabilities),
            token_digest=digest_secret(raw_worker_token),
        )
        session.add(worker)
        session.flush()
        _audit(
            session,
            event_type="worker.registered",
            worker_id=worker.id,
            payload={
                "capabilities": worker.capabilities,
                "protocol_version": worker.protocol_version,
            },
        )
        session.commit()
        return RegisteredWorker(worker.id, raw_worker_token, worker.protocol_version)
    except Exception:
        session.rollback()
        raise


def heartbeat(session: Session, *, worker_id: UUID, protocol_version: str) -> None:
    worker = session.get(WorkerRegistration, worker_id)
    if worker is None or worker.status != WorkerStatus.ACTIVE:
        raise WorkerProtocolError(401, "authentication_required")
    _require_protocol(protocol_version, worker.protocol_version)
    worker.last_heartbeat_at = utc_now()
    worker.updated_at = worker.last_heartbeat_at
    session.add(worker)
    _audit(session, event_type="worker.heartbeat", worker_id=worker.id, payload={})
    session.commit()


def _task_is_safe_monitor(task: ControlTask) -> bool:
    payload = task.payload
    expected_keys = {"task_type", "target_id", "endpoint", "timeout_seconds"}
    if (
        task.kind != TaskKind.CONTROL
        or not isinstance(payload, dict)
        or set(payload) != expected_keys
        or payload.get("task_type") != task.capability
        or not isinstance(payload.get("target_id"), str)
        or not isinstance(payload.get("timeout_seconds"), int)
        or isinstance(payload.get("timeout_seconds"), bool)
    ):
        return False
    target_id_value = cast(str, payload["target_id"])
    timeout_value = cast(int, payload["timeout_seconds"])
    if not 1 <= timeout_value <= 30:
        return False
    try:
        UUID(target_id_value)
        if task.capability == HTTP_MONITOR_CAPABILITY:
            validate_http_endpoint(str(payload["endpoint"]))
        elif task.capability == WINDOWS_SERVICE_MONITOR_CAPABILITY:
            validate_windows_service_name(str(payload["endpoint"]))
        else:
            return False
    except (TypeError, ValueError):
        return False
    return True


def _task_is_safe(task: ControlTask) -> bool:
    if task.capability in FILE_CAPABILITIES:
        model = cast(Any, {
            "file.inspect.v1": FileInspectTask,
            "file.quarantine.v1": FileQuarantineTask,
            "file.restore.v1": FileRestoreTask,
        }[task.capability])
        if task.kind != TaskKind.CONTROL or not isinstance(task.payload, dict):
            return False
        try:
            model.model_validate(task.payload)
        except ValidationError:
            return False
        return True
    return (
        task.kind == TaskKind.CONTROL
        and (
            task.capability == SELF_CHECK_CAPABILITY
            and task.payload == {"task_type": SELF_CHECK_CAPABILITY}
            or task.capability in {HTTP_MONITOR_CAPABILITY, WINDOWS_SERVICE_MONITOR_CAPABILITY}
            and _task_is_safe_monitor(task)
        )
    )


def claim_worker_task(
    session: Session, *, worker_id: UUID, protocol_version: str, capabilities: list[str]
) -> ControlTask | None:
    worker = session.get(WorkerRegistration, worker_id)
    if worker is None or worker.status != WorkerStatus.ACTIVE:
        raise WorkerProtocolError(401, "authentication_required")
    _require_protocol(protocol_version, worker.protocol_version)
    if set(capabilities) != set(worker.capabilities):
        raise WorkerProtocolError(403, "capability_mismatch")
    task = claim_next_task(
        session, worker_id=worker_id, capabilities=set(worker.capabilities), now=utc_now()
    )
    if task is None:
        session.commit()
        return None
    if not _task_is_safe(task):
        task.status = TaskStatus.MANUAL_REVIEW
        task.completed_at = utc_now()
        task.lease_owner_id = None
        task.lease_expires_at = None
        session.add(task)
        _audit(
            session,
            event_type="worker.task.rejected",
            worker_id=worker_id,
            payload={"task_id": str(task.id), "idempotency_key": task.idempotency_key},
        )
        session.commit()
        return None
    _audit(
        session,
        event_type="worker.task.claimed",
        worker_id=worker_id,
        payload={"task_id": str(task.id), "idempotency_key": task.idempotency_key},
    )
    session.commit()
    return task


def _owned_task(
    session: Session, *, task_id: UUID, worker_id: UUID, request_digest_value: str
) -> ControlTask:
    task = session.get(ControlTask, task_id)
    if task is None or not _task_is_safe(task):
        raise WorkerProtocolError(403, "task_not_authorized")
    if task.lease_owner_id != worker_id or task.lease_expires_at is None:
        raise WorkerProtocolError(403, "lease_not_owned")
    expiry = (
        task.lease_expires_at.replace(tzinfo=UTC)
        if task.lease_expires_at.tzinfo is None
        else task.lease_expires_at
    )
    if expiry <= utc_now():
        raise WorkerProtocolError(403, "lease_expired")
    if request_digest(task) != request_digest_value:
        raise WorkerProtocolError(403, "request_digest_mismatch")
    return task


def start_worker_task(
    session: Session,
    *,
    task_id: UUID,
    worker_id: UUID,
    protocol_version: str,
    request_digest_value: str,
) -> None:
    worker = session.get(WorkerRegistration, worker_id)
    if worker is None:
        raise WorkerProtocolError(401, "authentication_required")
    _require_protocol(protocol_version, worker.protocol_version)
    task = _owned_task(
        session, task_id=task_id, worker_id=worker_id, request_digest_value=request_digest_value
    )
    grant = session.get(WorkerExecutionGrant, task_id)
    if grant is not None:
        if grant.worker_id != worker_id or grant.request_digest != request_digest_value:
            raise WorkerProtocolError(409, "execution_grant_conflict")
        return
    if task.status != TaskStatus.LEASED:
        raise WorkerProtocolError(409, "task_not_startable")
    task.status = TaskStatus.RUNNING
    task.updated_at = utc_now()
    session.add(
        WorkerExecutionGrant(
            task_id=task.id,
            worker_id=worker_id,
            lease_version=task.lease_version,
            request_digest=request_digest_value,
            lease_expires_at=task.lease_expires_at,
        )
    )
    session.add(task)
    _audit(
        session,
        event_type="worker.task.started",
        worker_id=worker_id,
        payload={"task_id": str(task.id), "idempotency_key": task.idempotency_key},
    )
    session.commit()


def _grant_for_completion(
    session: Session, *, task_id: UUID, worker_id: UUID, lease_version: int,
    request_digest_value: str
) -> WorkerExecutionGrant:
    grant = session.get(WorkerExecutionGrant, task_id)
    if (
        grant is None
        or grant.worker_id != worker_id
        or grant.lease_version != lease_version
        or grant.request_digest != request_digest_value
    ):
        raise WorkerProtocolError(403, "execution_grant_not_owned")
    return grant


def complete_worker_task(
    session: Session,
    *,
    task_id: UUID,
    worker_id: UUID,
    protocol_version: str,
    request_digest_value: str,
    result: dict[str, object],
) -> ControlTask:
    worker = session.get(WorkerRegistration, worker_id)
    if worker is None:
        raise WorkerProtocolError(401, "authentication_required")
    _require_protocol(protocol_version, worker.protocol_version)
    task = session.get(ControlTask, task_id)
    if task is None:
        raise WorkerProtocolError(403, "task_not_authorized")
    safe_result = sanitize_result_for_task(task, result)
    if task is not None and task.status == TaskStatus.SUCCEEDED:
        _grant_for_completion(
            session, task_id=task_id, worker_id=worker_id,
            lease_version=task.lease_version, request_digest_value=request_digest_value
        )
        if task.result != safe_result:
            raise WorkerProtocolError(409, "result_replay_conflict")
        return task
    task = _owned_task(
        session, task_id=task_id, worker_id=worker_id, request_digest_value=request_digest_value
    )
    lease_expires_at = task.lease_expires_at
    if lease_expires_at is None:
        raise WorkerProtocolError(403, "lease_not_owned")
    if lease_expires_at.tzinfo is None:
        task.lease_expires_at = lease_expires_at.replace(tzinfo=UTC)
    grant = _grant_for_completion(
        session, task_id=task_id, worker_id=worker_id,
        lease_version=task.lease_version, request_digest_value=request_digest_value
    )
    try:
        completed = complete_task(
            session,
            task_id=task_id,
            worker_id=worker_id,
            lease_version=task.lease_version,
            outcome=TaskOutcome.SUCCEEDED,
            result=safe_result,
        )
    except ValueError as error:
        raise WorkerProtocolError(403, "task_not_completable") from error
    if completed.capability in {
        HTTP_MONITOR_CAPABILITY,
        WINDOWS_SERVICE_MONITOR_CAPABILITY,
    }:
        target_id = completed.payload.get("target_id")
        if not isinstance(target_id, str):
            raise WorkerProtocolError(422, "invalid_monitor_target")
        try:
            from app.services.monitoring import apply_probe_result

            apply_probe_result(
                session,
                target_id=UUID(target_id),
                result=safe_result,
                observed_at=completed.completed_at,
                task_id=completed.id,
            )
        except (TypeError, ValueError) as error:
            raise WorkerProtocolError(422, "invalid_monitor_target") from error
    grant.completed_at = utc_now()
    session.add(grant)
    append_outbox_event(
        session,
        event_type="task.updated",
        resource_type="task",
        resource_id=completed.id,
        payload={"status": completed.status.value, "task_id": str(completed.id)},
    )
    _audit(
        session,
        event_type="worker.task.completed",
        worker_id=worker_id,
        payload={"task_id": str(completed.id), "idempotency_key": completed.idempotency_key},
    )
    session.commit()
    return completed


def report_worker_result(
    session: Session,
    *,
    task_id: UUID,
    worker_id: UUID,
    protocol_version: str,
    request_digest_value: str,
    result: dict[str, object],
) -> ControlTask:
    completed = complete_worker_task(
        session,
        task_id=task_id,
        worker_id=worker_id,
        protocol_version=protocol_version,
        request_digest_value=request_digest_value,
        result=result,
    )
    if completed.status != TaskStatus.SUCCEEDED:
        raise WorkerProtocolError(409, "task_not_completed")
    return completed
