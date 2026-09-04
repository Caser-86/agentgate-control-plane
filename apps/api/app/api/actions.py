from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.api.runs import to_action_response
from app.auth.dependencies import require_operator
from app.auth.models import Operator
from app.db import get_session
from app.models import ActionStatus, RiskLevel, ToolAction
from app.schemas import ToolActionResponse

router = APIRouter(prefix="/api/actions", tags=["actions"])
SessionDep = Annotated[Session, Depends(get_session)]
OperatorDep = Annotated[Operator, Depends(require_operator)]


@router.get("", response_model=list[ToolActionResponse])
def list_actions(
    session: SessionDep,
    _: OperatorDep,
    status: Annotated[ActionStatus | None, Query()] = None,
    risk_level: Annotated[RiskLevel | None, Query()] = None,
) -> list[ToolActionResponse]:
    statement = select(ToolAction).order_by(cast(Any, ToolAction.created_at).desc()).limit(100)
    if status is not None:
        statement = statement.where(ToolAction.status == status)
    if risk_level is not None:
        statement = statement.where(ToolAction.risk_level == risk_level)
    return [to_action_response(action) for action in session.exec(statement).all()]


@router.get("/{action_id}", response_model=ToolActionResponse)
def get_action(action_id: UUID, session: SessionDep, _: OperatorDep) -> ToolActionResponse:
    action = session.get(ToolAction, action_id)
    if action is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "action was not found"},
        )
    return to_action_response(action)
