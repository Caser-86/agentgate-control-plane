from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.db import create_db_and_tables, create_db_engine
from app.models import utc_now
from app.monitoring.enums import EventStatus, ProbeStatus, TargetHealth, TargetKind
from app.monitoring.models import MonitorEvent, MonitorObservation, MonitorTarget
from app.services.monitoring import (
    apply_probe_result,
    validate_target_configuration,
)


def _target(**overrides: object) -> MonitorTarget:
    values: dict[str, object] = {
        "name": "本地 API",
        "kind": TargetKind.HTTP,
        "endpoint": "http://127.0.0.1:8000/health",
        "interval_seconds": 60,
        "timeout_seconds": 5,
        "failure_threshold": 3,
        "recovery_threshold": 2,
    }
    values.update(overrides)
    return MonitorTarget(**values)  # type: ignore[arg-type]


def test_target_configuration_accepts_loopback_http_and_safe_service_name() -> None:
    http = validate_target_configuration(
        kind=TargetKind.HTTP,
        endpoint="http://localhost:8000/health",
        interval_seconds=60,
        timeout_seconds=5,
        failure_threshold=3,
        recovery_threshold=2,
    )
    service = validate_target_configuration(
        kind=TargetKind.WINDOWS_SERVICE,
        endpoint="AgentGateWorker_01",
        interval_seconds=60,
        timeout_seconds=5,
        failure_threshold=3,
        recovery_threshold=2,
    )

    assert http.endpoint == "http://localhost:8000/health"
    assert service.endpoint == "AgentGateWorker_01"


@pytest.mark.parametrize(
    "kind, endpoint",
    [
        (TargetKind.HTTP, "https://example.com/health"),
        (TargetKind.HTTP, "ftp://127.0.0.1:8000/health"),
        (TargetKind.HTTP, "http://user:pass@127.0.0.1:8000/health"),
        (TargetKind.HTTP, "http://127.0.0.1:8000/health?token=secret"),
        (TargetKind.WINDOWS_SERVICE, "AgentGateWorker; powershell Remove-Item C:\\"),
        (TargetKind.WINDOWS_SERVICE, "C:\\Windows\\System32\\service.exe"),
    ],
)
def test_target_configuration_rejects_remote_or_command_like_values(
    kind: TargetKind, endpoint: str
) -> None:
    with pytest.raises(ValueError):
        validate_target_configuration(
            kind=kind,
            endpoint=endpoint,
            interval_seconds=60,
            timeout_seconds=5,
            failure_threshold=3,
            recovery_threshold=2,
        )


def test_target_configuration_enforces_bounded_monitoring_values() -> None:
    with pytest.raises(ValueError):
        validate_target_configuration(
            kind=TargetKind.HTTP,
            endpoint="http://127.0.0.1:8000/health",
            interval_seconds=1,
            timeout_seconds=5,
            failure_threshold=3,
            recovery_threshold=2,
        )


def test_failure_threshold_opens_one_event_and_recovery_threshold_closes_it() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        target = _target()
        session.add(target)
        session.commit()
        session.refresh(target)

        for _ in range(2):
            apply_probe_result(
                session,
                target_id=target.id,
                result={"status": ProbeStatus.FAILED.value, "detail": "HTTP 503"},
            )
        session.commit()
        assert target.health == TargetHealth.DEGRADED
        assert session.exec(select(MonitorEvent)).all() == []

        apply_probe_result(
            session,
            target_id=target.id,
            result={"status": ProbeStatus.FAILED.value, "detail": "HTTP 503"},
        )
        apply_probe_result(
            session,
            target_id=target.id,
            result={"status": ProbeStatus.FAILED.value, "detail": "HTTP 503"},
        )
        session.commit()
        events = session.exec(select(MonitorEvent)).all()
        assert target.health == TargetHealth.DOWN
        assert len(events) == 1
        assert events[0].status == EventStatus.ACTIVE

        apply_probe_result(
            session,
            target_id=target.id,
            result={"status": ProbeStatus.HEALTHY.value, "detail": "HTTP 200"},
        )
        session.commit()
        assert target.health == TargetHealth.DOWN
        assert target.consecutive_successes == 1
        assert session.get(MonitorEvent, events[0].id).status == EventStatus.ACTIVE

        apply_probe_result(
            session,
            target_id=target.id,
            result={"status": ProbeStatus.HEALTHY.value, "detail": "HTTP 200"},
        )
        session.commit()
        assert target.health == TargetHealth.HEALTHY
        closed = session.get(MonitorEvent, events[0].id)
        assert closed is not None
        assert closed.status == EventStatus.CLOSED
        assert closed.closed_at is not None
        assert len(session.exec(select(MonitorEvent)).all()) == 1


def test_unknown_probe_does_not_change_health_counters_or_active_event() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        target = _target()
        session.add(target)
        session.commit()
        session.refresh(target)
        apply_probe_result(
            session,
            target_id=target.id,
            result={"status": ProbeStatus.FAILED.value, "detail": "HTTP 503"},
        )
        apply_probe_result(
            session,
            target_id=target.id,
            result={"status": ProbeStatus.FAILED.value, "detail": "HTTP 503"},
        )
        apply_probe_result(
            session,
            target_id=target.id,
            result={"status": ProbeStatus.FAILED.value, "detail": "HTTP 503"},
        )
        session.commit()
        before = (target.health, target.consecutive_failures, target.consecutive_successes)

        apply_probe_result(
            session,
            target_id=target.id,
            result={"status": ProbeStatus.UNKNOWN.value, "detail": "探针不可用"},
        )
        session.commit()

        assert (target.health, target.consecutive_failures, target.consecutive_successes) == before
        active_events = session.exec(
            select(MonitorEvent).where(MonitorEvent.status == EventStatus.ACTIVE)
        ).all()
        assert len(active_events) == 1
        assert len(session.exec(select(MonitorObservation)).all()) == 4


def test_unknown_initial_probe_leaves_target_unknown() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        target = _target()
        session.add(target)
        session.commit()
        session.refresh(target)
        apply_probe_result(
            session,
            target_id=target.id,
            result={"status": ProbeStatus.UNKNOWN.value, "detail": "Worker 尚未准备好"},
        )
        session.commit()
        assert target.health == TargetHealth.UNKNOWN
        assert target.consecutive_failures == 0
        assert target.consecutive_successes == 0


def test_next_probe_time_is_scheduled_from_observation_time() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    observed_at = utc_now()
    with Session(engine) as session:
        target = _target(interval_seconds=120)
        session.add(target)
        session.commit()
        session.refresh(target)
        apply_probe_result(
            session,
            target_id=target.id,
            result={"status": ProbeStatus.HEALTHY.value, "latency_ms": 12},
            observed_at=observed_at,
        )
        session.commit()
        assert target.next_probe_at is not None
        next_probe_at = target.next_probe_at
        if next_probe_at.tzinfo is None:
            next_probe_at = next_probe_at.replace(tzinfo=observed_at.tzinfo)
        assert abs((next_probe_at - observed_at - timedelta(seconds=120)).total_seconds()) < 0.1
