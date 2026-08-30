from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.api.runs import to_audit_response
from app.db import get_session
from app.repositories import AuditRepository
from app.schemas import AuditEventResponse

router = APIRouter(prefix="/api/audit", tags=["audit"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[AuditEventResponse])
def list_audit(
    session: SessionDep,
    run_id: UUID | None = None,
    event_type: str | None = None,
    actor: str | None = None,
) -> list[AuditEventResponse]:
    return [
        to_audit_response(event)
        for event in AuditRepository(session).list(run_id, event_type, actor)
    ]


@router.get("/export")
def export_audit(
    session: SessionDep,
    run_id: UUID | None = None,
    event_type: str | None = None,
    actor: str | None = None,
) -> JSONResponse:
    events = AuditRepository(session).list(run_id, event_type, actor)
    payload = [to_audit_response(event).model_dump(mode="json") for event in events]
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": "attachment; filename=agentgate-audit.json"},
    )
