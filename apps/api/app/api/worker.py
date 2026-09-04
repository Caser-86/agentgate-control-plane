from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlmodel import Session

from app.auth.dependencies import WorkerIdentity, require_worker
from app.config import get_settings
from app.control.enums import TaskStatus
from app.control.models import ControlTask, WorkerExecutionGrant
from app.db import get_session
from app.services.worker_protocol import (
    MAX_RESULT_BYTES,
    ClaimRequest,
    CompleteTaskRequest,
    ProtocolRequest,
    RegisterWorkerRequest,
    TaskMutationRequest,
    WorkerProtocolError,
    claim_worker_task,
    complete_worker_task,
    heartbeat,
    register_worker,
    report_worker_result,
    request_digest,
    start_worker_task,
)
from app.services.workspaces import WorkspaceError, WorkspaceService

router = APIRouter(prefix="/api/v1/worker", tags=["worker"])
SessionDep = Annotated[Session, Depends(get_session)]
WorkerDep = Annotated[WorkerIdentity, Depends(require_worker)]


def _error(error: WorkerProtocolError) -> HTTPException:
    return HTTPException(
        error.status_code, detail={"code": error.code, "message": "Worker request denied"}
    )


def _bearer_token(request: Request) -> str:
    scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not token:
        raise HTTPException(
            401, detail={"code": "authentication_required", "message": "Worker request denied"}
        )
    return token


@router.post("/register", status_code=201)
def register(
    request: RegisterWorkerRequest, raw_request: Request, session: SessionDep
) -> dict[str, object]:
    try:
        registered = register_worker(session, request, _bearer_token(raw_request))
    except WorkerProtocolError as error:
        raise _error(error) from error
    return {
        "worker_id": str(registered.worker_id),
        "token": registered.token,
        "protocol_version": registered.protocol_version,
        "lease_seconds": get_settings().worker_lease_seconds,
        "max_journal_result_bytes": MAX_RESULT_BYTES,
    }


@router.post("/heartbeat", status_code=204)
def worker_heartbeat(request: ProtocolRequest, worker: WorkerDep, session: SessionDep) -> Response:
    try:
        heartbeat(
            session, worker_id=UUID(worker.worker_id), protocol_version=request.protocol_version
        )
    except WorkerProtocolError as error:
        raise _error(error) from error
    return Response(status_code=204)


@router.post("/claim")
def claim(
    request: ClaimRequest, worker: WorkerDep, session: SessionDep
) -> dict[str, object] | None:
    try:
        task = claim_worker_task(
            session,
            worker_id=UUID(worker.worker_id),
            protocol_version=request.protocol_version,
            capabilities=request.capabilities,
        )
    except WorkerProtocolError as error:
        raise _error(error) from error
    if task is None:
        return None
    return {
        "task_id": str(task.id),
        "idempotency_key": task.idempotency_key,
        "capability": task.capability,
        "request_digest": request_digest(task),
        "lease_expires_at": task.lease_expires_at,
        "payload": task.payload,
    }


@router.post("/tasks/{task_id}/start", status_code=204)
def start(
    task_id: UUID, request: TaskMutationRequest, worker: WorkerDep, session: SessionDep
) -> Response:
    try:
        start_worker_task(
            session,
            task_id=task_id,
            worker_id=UUID(worker.worker_id),
            protocol_version=request.protocol_version,
            request_digest_value=request.request_digest,
        )
    except WorkerProtocolError as error:
        raise _error(error) from error
    return Response(status_code=204)


def _complete_response(
    task_id: UUID, request: CompleteTaskRequest, worker: WorkerDep, session: SessionDep
) -> dict[str, object]:
    try:
        task = complete_worker_task(
            session,
            task_id=task_id,
            worker_id=UUID(worker.worker_id),
            protocol_version=request.protocol_version,
            request_digest_value=request.request_digest,
            result=request.result,
        )
    except WorkerProtocolError as error:
        raise _error(error) from error
    return {"task_id": str(task.id), "status": task.status.value}


@router.post("/tasks/{task_id}/complete")
def complete(
    task_id: UUID, request: CompleteTaskRequest, worker: WorkerDep, session: SessionDep
) -> dict[str, object]:
    return _complete_response(task_id, request, worker, session)


@router.post("/tasks/{task_id}/report")
def report(
    task_id: UUID, request: CompleteTaskRequest, worker: WorkerDep, session: SessionDep
) -> dict[str, object]:
    try:
        task = report_worker_result(
            session,
            task_id=task_id,
            worker_id=UUID(worker.worker_id),
            protocol_version=request.protocol_version,
            request_digest_value=request.request_digest,
            result=request.result,
        )
    except WorkerProtocolError as error:
        raise _error(error) from error
    return {"task_id": str(task.id), "status": task.status.value}


@router.get("/workspaces/{workspace_id}")
def worker_workspace_context(
    workspace_id: UUID,
    worker: WorkerDep,
    session: SessionDep,
    version: Annotated[int, Query(gt=0)],
    task_id: Annotated[UUID, Query()],
) -> dict[str, object]:
    task = session.get(ControlTask, task_id)
    worker_id = UUID(worker.worker_id)
    grant = session.get(WorkerExecutionGrant, task_id)
    if (
        task is None
        or task.capability not in worker.capabilities
        or task.capability not in {"file.inspect.v1", "file.quarantine.v1", "file.restore.v1"}
        or task.lease_owner_id != worker_id
        or task.status not in {TaskStatus.LEASED, TaskStatus.RUNNING}
        or grant is None
        or grant.worker_id != worker_id
    ):
        raise HTTPException(
            403,
            detail={"code": "worker_context_not_authorized", "message": "Worker 上下文授权无效"},
        )
    if task.payload.get("workspace_id") != str(workspace_id):
        raise HTTPException(
            403,
            detail={"code": "worker_context_not_authorized", "message": "Worker 上下文授权无效"},
        )
    if task.payload.get("workspace_version") != version:
        raise HTTPException(
            409,
            detail={"code": "workspace_version_conflict", "message": "工作区版本已变化"},
        )
    try:
        context = WorkspaceService(session).get_context(workspace_id, version)
    except WorkspaceError as error:
        raise HTTPException(
            error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    return {
        "workspace_id": str(context.id),
        "version": context.version,
        "root_path": context.root_path,
        "quarantine_root_path": context.quarantine_root_path,
        "protected_patterns": list(context.protected_patterns),
    }
