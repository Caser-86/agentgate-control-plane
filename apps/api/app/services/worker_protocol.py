import hashlib
import json
from dataclasses import dataclass
from datetime import UTC
from typing import Annotated, Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session, select

from app.auth.models import ClientToken
from app.auth.security import digest_secret, new_secret
from app.control.enums import TaskKind, TaskOutcome, TaskStatus, WorkerStatus
from app.control.models import ControlTask, WorkerExecutionGrant, WorkerRegistration
from app.control.repositories import claim_next_task, complete_task
from app.models import utc_now
from app.repositories import AuditRepository
from app.services.audit import AuditService

PROTOCOL_VERSION = "1.0"
SELF_CHECK_CAPABILITY = "platform.self_check"
SUPPORTED_CAPABILITIES = frozenset({SELF_CHECK_CAPABILITY})
MAX_RESULT_BYTES = 4096
MAX_CAPABILITIES = 1
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
        if len(set(value)) != len(value) or set(value) != SUPPORTED_CAPABILITIES:
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


def register_worker(
    session: Session, request: RegisterWorkerRequest, enrollment_token: str
) -> RegisteredWorker:
    _require_protocol(request.protocol_version, PROTOCOL_VERSION)
    enrollment = session.exec(
        select(ClientToken).where(
            ClientToken.token_digest == digest_secret(enrollment_token),
            cast(Any, ClientToken.revoked_at).is_(None),
        )
    ).first()
    if enrollment is None or "worker:enroll" not in enrollment.scopes:
        raise WorkerProtocolError(401, "invalid_enrollment_token")
    if enrollment.expires_at is not None:
        expires_at = enrollment.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= utc_now():
            raise WorkerProtocolError(401, "invalid_enrollment_token")
    raw_worker_token = new_secret()
    worker = WorkerRegistration(
        name=request.name,
        version=request.version,
        protocol_version=request.protocol_version,
        capabilities=sorted(request.capabilities),
        token_digest=digest_secret(raw_worker_token),
    )
    enrollment.revoked_at = utc_now()
    session.add(worker)
    session.add(enrollment)
    session.flush()
    _audit(
        session,
        event_type="worker.registered",
        worker_id=worker.id,
        payload={"capabilities": worker.capabilities, "protocol_version": worker.protocol_version},
    )
    session.commit()
    return RegisteredWorker(worker.id, raw_worker_token, worker.protocol_version)


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


def _task_is_safe_self_check(task: ControlTask) -> bool:
    return (
        task.kind == TaskKind.CONTROL
        and task.capability == SELF_CHECK_CAPABILITY
        and task.payload == {"task_type": SELF_CHECK_CAPABILITY}
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
    if not _task_is_safe_self_check(task):
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
    if task is None or not _task_is_safe_self_check(task):
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
    session: Session, *, task_id: UUID, worker_id: UUID, request_digest_value: str
) -> WorkerExecutionGrant:
    grant = session.get(WorkerExecutionGrant, task_id)
    if (
        grant is None
        or grant.worker_id != worker_id
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
    safe_result = sanitize_self_check_result(result)
    task = session.get(ControlTask, task_id)
    if task is not None and task.status == TaskStatus.SUCCEEDED:
        _grant_for_completion(
            session, task_id=task_id, worker_id=worker_id, request_digest_value=request_digest_value
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
        session, task_id=task_id, worker_id=worker_id, request_digest_value=request_digest_value
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
    grant.completed_at = utc_now()
    session.add(grant)
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
