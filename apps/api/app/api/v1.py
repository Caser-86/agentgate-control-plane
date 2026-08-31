from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlmodel import Session, select

from app.auth.dependencies import ClientIdentity, require_client_scope
from app.control.enums import SideEffectCertainty, TaskKind
from app.control.models import ControlTask
from app.control.repositories import append_outbox_event, enqueue_task_with_status
from app.db import get_session
from app.policy import PolicyEngine
from app.repositories import AuditRepository
from app.schemas import (
    ActionProposalRequest,
    CheckProposalRequest,
    EventProposalRequest,
    ProposalResponse,
    TaskStatusResponse,
)
from app.services.audit import AuditService, redact
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
    if request.check_type == "platform.self_check":
        if request.target != "local" or request.parameters:
            AuditService(AuditRepository(session)).append(
                event_type="check.rejected",
                actor=client.actor,
                payload={
                    "check_type": request.check_type,
                    "target": request.target,
                    "reason": "self_check_requires_local_without_parameters",
                },
                resource_type="check_proposal",
                resource_id=uuid4(),
            )
            raise _deny("invalid_self_check_target")
        registered = ToolRegistry().get(request.check_type)
    else:
        registered, _ = _validate_registered_target(
            ToolRegistry(), request.check_type, request.target, request.parameters
        )
    if not registered.spec.read_only:
        raise _deny("check_must_be_read_only")
    if request.check_type != "platform.self_check":
        AuditService(AuditRepository(session)).append(
            event_type="check.rejected",
            actor=client.actor,
            payload={
                "check_type": request.check_type,
                "target": request.target,
                "reason": "unsupported_phase_zero_check",
            },
            resource_type="check_proposal",
            resource_id=uuid4(),
        )
        raise _deny("unsupported_check")
    payload: dict[str, object] = {"task_type": "platform.self_check"}
    task, created = enqueue_task_with_status(
        session,
        kind=TaskKind.CONTROL,
        payload=payload,
        idempotency_key=request.idempotency_key,
        capability="platform.self_check",
        side_effect_certainty=SideEffectCertainty.READ_ONLY,
        proposer_client_id=UUID(client.token_id),
    )
    if created:
        AuditService(AuditRepository(session)).append(
            event_type="check.accepted",
            actor=client.actor,
            payload={"check_type": request.check_type, "target": request.target},
            resource_type="control_task",
            resource_id=task.id,
            commit=False,
        )
        append_outbox_event(
            session,
            event_type="task.queued",
            resource_type="control_task",
            resource_id=task.id,
            payload={"task_id": str(task.id), "capability": task.capability},
        )
    session.commit()
    session.refresh(task)
    return ProposalResponse(id=task.id)


@router.get("/checks/{check_id}", response_model=TaskStatusResponse)
def get_check_status(
    check_id: UUID, client: CheckClientDep, session: SessionDep
) -> TaskStatusResponse:
    task = session.exec(
        select(ControlTask).where(
            ControlTask.id == check_id,
            ControlTask.kind == TaskKind.CONTROL,
            ControlTask.capability == "platform.self_check",
            ControlTask.proposer_client_id == UUID(client.token_id),
        )
    ).first()
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "check was not found"},
        )
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
