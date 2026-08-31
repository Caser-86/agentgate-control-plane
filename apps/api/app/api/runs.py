import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.auth.dependencies import require_csrf, require_operator
from app.auth.models import Operator
from app.config import get_settings
from app.db import get_engine, get_session
from app.models import AgentRun, AuditEvent, ToolAction
from app.repositories import ActionRepository, AuditRepository, RunRepository
from app.schemas import (
    AgentRunResponse,
    AuditEventResponse,
    CreateRunRequest,
    RunDetailResponse,
    ToolActionResponse,
)
from app.services.audit import redact
from app.services.outbox import effective_cursor, stream_outbox_events
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
    background_tasks: BackgroundTasks,
    session: SessionDep,
    _: CsrfOperatorDep,
) -> AgentRunResponse:
    try:
        run = RunService(session, get_settings()).create(request.user_request, background_tasks)
    except RuntimeError as exc:
        logger.warning("run_provider_creation_failed", exc_info=False)
        raise HTTPException(
            status_code=503,
            detail={"code": "provider_error", "message": "Provider unavailable"},
        ) from exc
    return to_run_response(run)


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


def stream_run_events(run_id: UUID, cursor: int) -> AsyncIterator[str]:
    return stream_outbox_events(lambda: Session(get_engine()), cursor=cursor, resource_id=run_id)


@router.get("/{run_id}/events")
async def run_events(
    run_id: UUID,
    session: SessionDep,
    _: OperatorDep,
    after: Annotated[str | None, Query()] = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    if RunRepository(session).get(run_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "run was not found"},
        )
    return StreamingResponse(
        stream_run_events(run_id, effective_cursor(last_event_id=last_event_id, after=after)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
