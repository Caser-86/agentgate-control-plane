import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.auth.dependencies import require_csrf, require_operator
from app.auth.models import Operator
from app.config import get_settings
from app.control.models import ControlTask
from app.db import get_session
from app.models import AgentRun, AuditEvent, ToolAction
from app.repositories import ActionRepository, AuditRepository, RunRepository
from app.schemas import (
    AgentRunResponse,
    AuditEventResponse,
    CreateRunRequest,
    RunDetailResponse,
    TaskStatusResponse,
    ToolActionResponse,
)
from app.services.audit import redact
from app.services.outbox import MAX_EVENT_BATCH, effective_cursor, stream_outbox_events
from app.services.runs import RunService

router = APIRouter(prefix="/api/runs", tags=["runs"])
logger = logging.getLogger(__name__)
SessionDep = Annotated[Session, Depends(get_session)]
OperatorDep = Annotated[Operator, Depends(require_operator)]
CsrfOperatorDep = Annotated[Operator, Depends(require_csrf)]


def _parse_json(value: str | None) -> object | None:
    if value is None:
        return None
    try:
        return cast(object, json.loads(value))
    except json.JSONDecodeError:
        return {"raw": value}


def to_run_response(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse.model_validate(run, from_attributes=True)


def to_action_response(action: ToolAction) -> ToolActionResponse:
    arguments = _parse_json(action.arguments_json)
    safe_arguments = redact(arguments)
    safe_result = redact(_parse_json(action.result_json))
    return ToolActionResponse(
        id=action.id,
        run_id=action.run_id,
        tool_call_id=action.tool_call_id,
        tool_name=action.tool_name,
        risk_level=action.risk_level.value,
        policy_decision=action.policy_decision.value,
        status=action.status.value,
        arguments=safe_arguments if isinstance(safe_arguments, dict) else {},
        result=safe_result,
        reason=action.reason,
        created_at=action.created_at,
        decided_at=action.decided_at,
        executed_at=action.executed_at,
    )


def to_audit_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        id=event.id,
        run_id=event.run_id,
        action_id=event.action_id,
        event_type=event.event_type,
        actor=event.actor,
        payload=redact(_parse_json(event.payload_json) or {}),
        created_at=event.created_at,
    )


def _final_text(run: AgentRun) -> str | None:
    for message in reversed(run.messages()):
        if message.get("role") == "assistant" and isinstance(message.get("content"), str):
            return str(message["content"])
    return None


@router.post("", response_model=AgentRunResponse, status_code=202)
def create_run(
    request: CreateRunRequest,
    session: SessionDep,
    operator: CsrfOperatorDep,
) -> AgentRunResponse:
    try:
        run = RunService(session, get_settings()).create(request.user_request, operator)
    except RuntimeError as exc:
        logger.warning("run_provider_creation_failed", exc_info=False)
        raise HTTPException(
            status_code=503,
            detail={"code": "provider_error", "message": "Provider unavailable"},
        ) from exc
    return to_run_response(run)


def to_task_response(task: ControlTask) -> TaskStatusResponse:
    return TaskStatusResponse(
        id=task.id,
        kind=task.kind.value,
        status=task.status.value,
        attempts=task.attempts,
        run_id=task.run_id,
        available_at=task.available_at,
        lease_expires_at=task.lease_expires_at,
        result=redact(task.result),
    )


@router.get("", response_model=list[AgentRunResponse])
def list_runs(session: SessionDep, _: OperatorDep) -> list[AgentRunResponse]:
    return [to_run_response(run) for run in RunRepository(session).list()]


@router.get("/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: UUID, session: SessionDep, _: OperatorDep) -> RunDetailResponse:
    run = RunRepository(session).get(run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "run was not found"},
        )
    return RunDetailResponse(
        **to_run_response(run).model_dump(),
        actions=[
            to_action_response(action) for action in ActionRepository(session).list_for_run(run_id)
        ],
        audit_events=[to_audit_response(event) for event in AuditRepository(session).list(run_id)],
        final_text=_final_text(run),
    )


@router.get("/{run_id}/tasks", response_model=list[TaskStatusResponse])
def list_run_tasks(run_id: UUID, session: SessionDep, _: OperatorDep) -> list[TaskStatusResponse]:
    if RunRepository(session).get(run_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "run was not found"},
        )
    from sqlmodel import select

    tasks = list(session.exec(select(ControlTask).where(ControlTask.run_id == run_id)).all())
    return [to_task_response(task) for task in tasks]


def stream_run_events(
    run_id: UUID, cursor: int, session: Session, limit: int | None = None
) -> AsyncIterator[str]:
    bind = session.get_bind()
    return stream_outbox_events(
        lambda: Session(bind), cursor=cursor, resource_id=run_id, max_events=limit
    )


@router.get("/{run_id}/events")
async def run_events(
    run_id: UUID,
    session: SessionDep,
    _: OperatorDep,
    after: Annotated[str | None, Query()] = None,
    last_event_id: Annotated[str | None, Header()] = None,
    limit: Annotated[int | None, Query(ge=1, le=MAX_EVENT_BATCH)] = None,
) -> StreamingResponse:
    if RunRepository(session).get(run_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "run was not found"},
        )
    return StreamingResponse(
        stream_run_events(
            run_id,
            effective_cursor(last_event_id=last_event_id, after=after),
            session,
            limit,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
