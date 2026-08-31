from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel import Session

from app.auth.dependencies import WorkerIdentity, require_worker
from app.config import get_settings
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
