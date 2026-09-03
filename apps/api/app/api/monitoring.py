from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from app.auth.dependencies import require_csrf, require_operator
from app.auth.models import Operator
from app.control.enums import SideEffectCertainty, TaskKind
from app.control.repositories import enqueue_task_with_status
from app.db import get_session
from app.models import utc_now
from app.monitoring.enums import EventStatus, TargetKind
from app.monitoring.models import MonitorEvent, MonitorTarget
from app.repositories import AuditRepository
from app.services.audit import AuditService
from app.services.monitoring import capability_for_kind, validate_target_configuration

router = APIRouter(prefix="/api/monitor", tags=["monitoring"])
SessionDep = Annotated[Session, Depends(get_session)]
OperatorDep = Annotated[Operator, Depends(require_operator)]
WriteOperatorDep = Annotated[Operator, Depends(require_csrf)]


class TargetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=128)]
    kind: TargetKind
    endpoint: Annotated[str, Field(min_length=1, max_length=2048)]
    enabled: bool = True
    interval_seconds: int = Field(default=60, ge=1, le=86_400)
    timeout_seconds: int = Field(default=5, ge=1, le=30)
    failure_threshold: int = Field(default=3, ge=1, le=10)
    recovery_threshold: int = Field(default=2, ge=1, le=10)


def _invalid_target(error: ValueError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": "invalid_target", "message": str(error)},
    )


def _event_response(event: MonitorEvent) -> dict[str, object]:
    return {
        "id": str(event.id),
        "target_id": str(event.target_id),
        "status": event.status,
        "reason": event.reason,
        "failure_count": event.failure_count,
        "opened_at": event.opened_at,
        "updated_at": event.updated_at,
        "last_failure_at": event.last_failure_at,
        "closed_at": event.closed_at,
    }


def _target_response(session: Session, target: MonitorTarget) -> dict[str, object]:
    active_event = session.exec(
        select(MonitorEvent).where(
            MonitorEvent.target_id == target.id,
            MonitorEvent.status == EventStatus.ACTIVE.value,
        )
    ).first()
    return {
        "id": str(target.id),
        "name": target.name,
        "kind": target.kind,
        "endpoint": target.endpoint,
        "enabled": target.enabled,
        "interval_seconds": target.interval_seconds,
        "timeout_seconds": target.timeout_seconds,
        "failure_threshold": target.failure_threshold,
        "recovery_threshold": target.recovery_threshold,
        "health": target.health,
        "consecutive_failures": target.consecutive_failures,
        "consecutive_successes": target.consecutive_successes,
        "last_probe_status": target.last_probe_status,
        "last_probe_detail": target.last_probe_detail,
        "last_latency_ms": target.last_latency_ms,
        "last_probe_at": target.last_probe_at,
        "next_probe_at": target.next_probe_at,
        "created_at": target.created_at,
        "updated_at": target.updated_at,
        "active_event": _event_response(active_event) if active_event else None,
    }


@router.get("/targets")
def list_targets(session: SessionDep, _: OperatorDep) -> list[dict[str, object]]:
    created_at = cast(Any, MonitorTarget.created_at)
    targets = session.exec(select(MonitorTarget).order_by(created_at.desc())).all()
    return [_target_response(session, target) for target in targets]


@router.post("/targets", status_code=201)
def create_target(
    request: TargetCreateRequest, session: SessionDep, operator: WriteOperatorDep
) -> dict[str, object]:
    try:
        configuration = validate_target_configuration(
            kind=request.kind,
            endpoint=request.endpoint,
            interval_seconds=request.interval_seconds,
            timeout_seconds=request.timeout_seconds,
            failure_threshold=request.failure_threshold,
            recovery_threshold=request.recovery_threshold,
        )
    except ValueError as error:
        raise _invalid_target(error) from error
    target = MonitorTarget(
        name=request.name,
        kind=configuration.kind.value,
        endpoint=configuration.endpoint,
        enabled=request.enabled,
        interval_seconds=configuration.interval_seconds,
        timeout_seconds=configuration.timeout_seconds,
        failure_threshold=configuration.failure_threshold,
        recovery_threshold=configuration.recovery_threshold,
        next_probe_at=utc_now(),
    )
    session.add(target)
    session.flush()
    AuditService(AuditRepository(session)).append(
        event_type="monitor.target.created",
        actor=f"operator:{operator.id}",
        payload={"kind": target.kind},
        resource_type="monitor_target",
        resource_id=target.id,
        commit=False,
    )
    session.commit()
    session.refresh(target)
    return _target_response(session, target)


@router.get("/targets/{target_id}")
def get_target(target_id: UUID, session: SessionDep, _: OperatorDep) -> dict[str, object]:
    target = session.get(MonitorTarget, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "目标不存在"})
    return _target_response(session, target)


@router.post("/targets/{target_id}/probe", status_code=202)
def probe_target(target_id: UUID, session: SessionDep, _: WriteOperatorDep) -> dict[str, object]:
    target = session.get(MonitorTarget, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "目标不存在"})
    if not target.enabled:
        raise HTTPException(
            status_code=409,
            detail={"code": "target_disabled", "message": "目标已禁用"},
        )
    capability = capability_for_kind(target.kind)
    task, created = enqueue_task_with_status(
        session,
        kind=TaskKind.CONTROL,
        payload={
            "task_type": capability,
            "target_id": str(target.id),
            "endpoint": target.endpoint,
            "timeout_seconds": target.timeout_seconds,
        },
        idempotency_key=f"manual-monitor-probe:{target.id}:{uuid4()}",
        capability=capability,
        side_effect_certainty=SideEffectCertainty.READ_ONLY,
    )
    del created
    session.commit()
    session.refresh(task)
    return {"task_id": str(task.id), "target_id": str(target.id), "status": task.status.value}


@router.get("/events")
def list_events(
    session: SessionDep,
    _: OperatorDep,
    target_id: UUID | None = None,
    active_only: bool = Query(default=False),
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[dict[str, object]]:
    opened_at = cast(Any, MonitorEvent.opened_at)
    statement = select(MonitorEvent).order_by(opened_at.desc()).limit(limit)
    if target_id is not None:
        statement = statement.where(MonitorEvent.target_id == target_id)
    if active_only:
        statement = statement.where(MonitorEvent.status == EventStatus.ACTIVE.value)
    return [_event_response(event) for event in session.exec(statement).all()]
