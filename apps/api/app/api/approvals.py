from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.runs import to_action_response
from app.db import get_session
from app.schemas import ApprovalRequest, ToolActionResponse
from app.services.approvals import (
    ApprovalConflictError,
    ApprovalNotFoundError,
    ApprovalService,
)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])
SessionDep = Annotated[Session, Depends(get_session)]


async def _decide(
    action_id: UUID,
    request: ApprovalRequest,
    session: Session,
    approved: bool,
) -> ToolActionResponse:
    service = ApprovalService(session)
    try:
        action = (
            await service.approve(action_id, request.actor, request.note)
            if approved
            else await service.deny(action_id, request.actor, request.note)
        )
    except ApprovalNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc
    except ApprovalConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "approval_conflict", "message": str(exc)},
        ) from exc
    return to_action_response(action)


@router.post("/{action_id}/approve", response_model=ToolActionResponse)
async def approve_action(
    action_id: UUID,
    request: ApprovalRequest,
    session: SessionDep,
) -> ToolActionResponse:
    return await _decide(action_id, request, session, True)


@router.post("/{action_id}/deny", response_model=ToolActionResponse)
async def deny_action(
    action_id: UUID,
    request: ApprovalRequest,
    session: SessionDep,
) -> ToolActionResponse:
    return await _decide(action_id, request, session, False)
