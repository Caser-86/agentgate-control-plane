from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.runs import to_action_response
from app.auth.dependencies import require_csrf
from app.auth.models import Operator
from app.db import get_session
from app.models import ActionStatus, ToolAction
from app.schemas import ApprovalRequest, ToolActionResponse
from app.services.approvals import (
    ApprovalConflictError,
    ApprovalNotFoundError,
    ApprovalService,
)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])
SessionDep = Annotated[Session, Depends(get_session)]
OperatorDep = Annotated[Operator, Depends(require_csrf)]


@router.get("", response_model=list[ToolActionResponse])
def list_approvals(session: SessionDep, _: OperatorDep) -> list[ToolActionResponse]:
    actions = session.exec(
        select(ToolAction)
        .where(ToolAction.status == ActionStatus.PENDING_APPROVAL)
        .order_by(cast(Any, ToolAction.created_at).desc())
        .limit(100)
    ).all()
    return [to_action_response(action) for action in actions]


def _decide(
    action_id: UUID,
    request: ApprovalRequest,
    session: Session,
    approved: bool,
    operator: Operator,
) -> ToolActionResponse:
    service = ApprovalService(session)
    try:
        from app.services.approvals import ApprovalDecision

        action = service.decide(
            action_id,
            ApprovalDecision.APPROVED if approved else ApprovalDecision.DENIED,
            operator,
            request.note,
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
def approve_action(
    action_id: UUID,
    request: ApprovalRequest,
    session: SessionDep,
    operator: OperatorDep,
) -> ToolActionResponse:
    return _decide(action_id, request, session, True, operator)


@router.post("/{action_id}/deny", response_model=ToolActionResponse)
def deny_action(
    action_id: UUID,
    request: ApprovalRequest,
    session: SessionDep,
    operator: OperatorDep,
) -> ToolActionResponse:
    return _decide(action_id, request, session, False, operator)
