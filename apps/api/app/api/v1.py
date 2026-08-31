from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlmodel import Session

from app.auth.dependencies import ClientIdentity, require_client_scope
from app.control.enums import SideEffectCertainty, TaskKind
from app.control.repositories import enqueue_task
from app.db import get_session
from app.policy import PolicyEngine
from app.repositories import AuditRepository
from app.schemas import (
    ActionProposalRequest,
    CheckProposalRequest,
    EventProposalRequest,
    ProposalResponse,
)
from app.services.audit import AuditService
from app.tools.registry import RegisteredTool, ToolRegistry, UnknownToolError

router = APIRouter(prefix="/api/v1", tags=["v1"])
SessionDep = Annotated[Session, Depends(get_session)]
EventClientDep = Annotated[ClientIdentity, Depends(require_client_scope("propose:events"))]
CheckClientDep = Annotated[ClientIdentity, Depends(require_client_scope("propose:checks"))]
ActionClientDep = Annotated[ClientIdentity, Depends(require_client_scope("propose:actions"))]


def _deny(code: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": code, "message": "Proposal denied"})


def _validate_registered_target(
    registry: ToolRegistry, action_type: str, target: str, parameters: dict[str, object]
) -> tuple[RegisteredTool, dict[str, object]]:
    try:
        registered = registry.get(action_type)
    except UnknownToolError as exc:
        raise _deny("unknown_action") from exc
    normalized = {**parameters, "service": target}
    try:
        registry.validate(action_type, normalized)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_proposal", "message": "Proposal parameters are invalid"},
        ) from exc
    return registered, normalized


@router.post("/events", response_model=ProposalResponse, status_code=201)
def propose_event(
    request: EventProposalRequest, client: EventClientDep, session: SessionDep
) -> ProposalResponse:
    event = AuditService(AuditRepository(session)).append(
        event_type="adapter.event.proposed",
        actor=client.actor,
        payload={"event_type": request.event_type, "payload": request.payload},
        resource_type="adapter_event",
        resource_id=uuid4(),
    )
    return ProposalResponse(id=event.id)


@router.post("/checks", response_model=ProposalResponse, status_code=201)
def propose_check(
    request: CheckProposalRequest, client: CheckClientDep, session: SessionDep
) -> ProposalResponse:
    registered, normalized = _validate_registered_target(
        ToolRegistry(), request.check_type, request.target, request.parameters
    )
    if not registered.spec.read_only:
        raise _deny("check_must_be_read_only")
    payload: dict[str, object] = (
        {"task_type": "platform.self_check"}
        if request.check_type == "platform.self_check"
        else cast(dict[str, object], {
            "check_type": request.check_type,
            "target": request.target,
            "parameters": normalized,
            "actor": client.actor,
        })
    )
    capability = (
        "platform.self_check" if request.check_type == "platform.self_check" else "check"
    )
    task = enqueue_task(
        session,
        kind=TaskKind.CONTROL,
        payload=payload,
        idempotency_key=request.idempotency_key,
        capability=capability,
        side_effect_certainty=SideEffectCertainty.READ_ONLY,
    )
    session.commit()
    session.refresh(task)
    return ProposalResponse(id=task.id)


@router.post("/actions", response_model=ProposalResponse)
def propose_action(
    request: ActionProposalRequest, _: ActionClientDep, session: SessionDep
) -> ProposalResponse:
    del session
    registered, normalized = _validate_registered_target(
        ToolRegistry(), request.action_type, request.target, request.parameters
    )
    decision = PolicyEngine().evaluate(registered.spec, normalized).decision.value
    external_decision = {
        "auto_approve": "allow_auto",
        "require_approval": "require_approval",
        "deny": "deny",
    }[decision]
    return ProposalResponse(decision=external_decision)
