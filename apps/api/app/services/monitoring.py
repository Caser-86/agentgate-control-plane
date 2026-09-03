import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from sqlmodel import Session, select

from app.models import utc_now
from app.monitoring.enums import (
    HTTP_MONITOR_CAPABILITY,
    WINDOWS_SERVICE_MONITOR_CAPABILITY,
    EventStatus,
    ProbeStatus,
    TargetHealth,
    TargetKind,
)
from app.monitoring.models import MonitorEvent, MonitorObservation, MonitorTarget
from app.repositories import AuditRepository
from app.services.audit import AuditService

MIN_INTERVAL_SECONDS = 5
MAX_INTERVAL_SECONDS = 86_400
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 30
MIN_THRESHOLD = 1
MAX_THRESHOLD = 10
MAX_DETAIL_LENGTH = 512
SERVICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


@dataclass(frozen=True)
class ValidatedTargetConfiguration:
    kind: TargetKind
    endpoint: str
    interval_seconds: int
    timeout_seconds: int
    failure_threshold: int
    recovery_threshold: int


def _bounded_int(name: str, value: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def validate_http_endpoint(endpoint: str) -> str:
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("HTTP endpoint is required")
    try:
        parsed = urlsplit(endpoint)
        hostname = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise ValueError("HTTP endpoint must be a valid loopback URL") from error
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("HTTP endpoint must be a valid loopback URL")
    normalized_host = hostname.lower().rstrip(".")
    is_loopback = normalized_host == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(normalized_host).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise ValueError("HTTP endpoint must target a loopback host")
    if port is not None and not 1 <= port <= 65_535:
        raise ValueError("HTTP endpoint port must be between 1 and 65535")
    return endpoint.strip()


def validate_windows_service_name(endpoint: str) -> str:
    if not isinstance(endpoint, str) or SERVICE_NAME_PATTERN.fullmatch(endpoint.strip()) is None:
        raise ValueError("Windows service name must contain only letters, numbers, '.', '_' or '-'")
    return endpoint.strip()


def validate_target_configuration(
    *,
    kind: TargetKind | str,
    endpoint: str,
    interval_seconds: int,
    timeout_seconds: int,
    failure_threshold: int,
    recovery_threshold: int,
) -> ValidatedTargetConfiguration:
    try:
        target_kind = TargetKind(kind)
    except ValueError as error:
        raise ValueError("unsupported monitoring target kind") from error
    normalized_endpoint = (
        validate_http_endpoint(endpoint)
        if target_kind == TargetKind.HTTP
        else validate_windows_service_name(endpoint)
    )
    return ValidatedTargetConfiguration(
        kind=target_kind,
        endpoint=normalized_endpoint,
        interval_seconds=_bounded_int(
            "interval_seconds", interval_seconds, MIN_INTERVAL_SECONDS, MAX_INTERVAL_SECONDS
        ),
        timeout_seconds=_bounded_int(
            "timeout_seconds", timeout_seconds, MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS
        ),
        failure_threshold=_bounded_int(
            "failure_threshold", failure_threshold, MIN_THRESHOLD, MAX_THRESHOLD
        ),
        recovery_threshold=_bounded_int(
            "recovery_threshold", recovery_threshold, MIN_THRESHOLD, MAX_THRESHOLD
        ),
    )


def capability_for_kind(kind: TargetKind | str) -> str:
    target_kind = TargetKind(kind)
    return (
        HTTP_MONITOR_CAPABILITY
        if target_kind == TargetKind.HTTP
        else WINDOWS_SERVICE_MONITOR_CAPABILITY
    )


def _safe_detail(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value[:MAX_DETAIL_LENGTH]


def normalize_probe_result(result: dict[str, object]) -> dict[str, object]:
    if not isinstance(result, dict):
        raise ValueError("probe result must be an object")
    try:
        status = ProbeStatus(str(result.get("status")))
    except ValueError as error:
        raise ValueError("probe result has an unsupported status") from error
    safe: dict[str, object] = {"status": status.value, "detail": _safe_detail(result.get("detail"))}
    latency_ms = result.get("latency_ms")
    if (
        isinstance(latency_ms, int)
        and not isinstance(latency_ms, bool)
        and 0 <= latency_ms <= 60_000
    ):
        safe["latency_ms"] = latency_ms
    return safe


def _active_event(session: Session, target_id: UUID) -> MonitorEvent | None:
    return session.exec(
        select(MonitorEvent).where(
            MonitorEvent.target_id == target_id,
            MonitorEvent.status == EventStatus.ACTIVE.value,
        )
    ).first()


def _record_audit(
    session: Session, *, event_type: str, target_id: UUID, payload: dict[str, object]
) -> None:
    AuditService(AuditRepository(session)).append(
        event_type=event_type,
        actor="monitoring",
        payload=payload,
        resource_type="monitor_target",
        resource_id=target_id,
        commit=False,
    )


def apply_probe_result(
    session: Session,
    *,
    target_id: UUID,
    result: dict[str, object],
    observed_at: datetime | None = None,
    task_id: UUID | None = None,
) -> MonitorTarget:
    target = session.get(MonitorTarget, target_id)
    if target is None:
        raise ValueError("monitor target was not found")
    safe = normalize_probe_result(result)
    when = observed_at or utc_now()
    status = ProbeStatus(str(safe["status"]))
    previous_status = target.last_probe_status
    target.last_probe_status = status.value
    target.last_probe_detail = str(safe.get("detail", ""))
    latency_ms = safe.get("latency_ms")
    target.last_latency_ms = latency_ms if isinstance(latency_ms, int) else None
    target.last_probe_at = when
    target.next_probe_at = when + timedelta(seconds=target.interval_seconds)
    observation = MonitorObservation(
        target_id=target.id,
        task_id=task_id,
        status=status.value,
        detail=target.last_probe_detail or "",
        latency_ms=target.last_latency_ms,
        observed_at=when,
    )
    session.add(observation)
    active_event = _active_event(session, target.id)

    if status == ProbeStatus.UNKNOWN:
        if previous_status is None:
            target.health = TargetHealth.UNKNOWN.value
    elif status == ProbeStatus.FAILED:
        target.consecutive_failures += 1
        target.consecutive_successes = 0
        if target.health != TargetHealth.DOWN.value:
            target.health = (
                TargetHealth.DOWN.value
                if target.consecutive_failures >= target.failure_threshold
                else TargetHealth.DEGRADED.value
            )
        if target.health == TargetHealth.DOWN.value:
            if active_event is None:
                active_event = MonitorEvent(
                    target_id=target.id,
                    status=EventStatus.ACTIVE.value,
                    reason=target.last_probe_detail or "探测失败",
                    failure_count=target.consecutive_failures,
                    opened_at=when,
                    updated_at=when,
                    last_failure_at=when,
                )
                session.add(active_event)
                session.flush()
                _record_audit(
                    session,
                    event_type="monitor.event.opened",
                    target_id=target.id,
                    payload={"event_id": str(active_event.id), "reason": active_event.reason},
                )
            else:
                active_event.reason = target.last_probe_detail or active_event.reason
                active_event.failure_count = target.consecutive_failures
                active_event.last_failure_at = when
                active_event.updated_at = when
                session.add(active_event)
    else:
        target.consecutive_failures = 0
        target.consecutive_successes += 1
        if target.health == TargetHealth.DOWN.value:
            if target.consecutive_successes >= target.recovery_threshold:
                target.health = TargetHealth.HEALTHY.value
                if active_event is not None:
                    active_event.status = EventStatus.CLOSED.value
                    active_event.closed_at = when
                    active_event.updated_at = when
                    session.add(active_event)
                    _record_audit(
                        session,
                        event_type="monitor.event.closed",
                        target_id=target.id,
                        payload={"event_id": str(active_event.id), "reason": "目标已恢复"},
                    )
        else:
            target.health = TargetHealth.HEALTHY.value

    target.updated_at = when
    session.add(target)
    _record_audit(
        session,
        event_type="monitor.probe.recorded",
        target_id=target.id,
        payload={
            "status": status.value,
            "detail": target.last_probe_detail or "",
            "latency_ms": target.last_latency_ms,
        },
    )
    return target
