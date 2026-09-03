from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.auth.models import ClientToken
from app.auth.security import digest_secret
from app.control.enums import TaskKind, TaskStatus
from app.control.models import ControlTask, WorkerRegistration
from app.models import utc_now
from app.monitoring.enums import TargetHealth, TargetKind
from app.monitoring.models import MonitorTarget
from app.processes.scheduler import discover_due_tasks
from app.services.worker_protocol import PROTOCOL_VERSION
from tests.conftest import authenticate_client


def test_monitoring_routes_require_operator_session(
    auth_client: tuple[TestClient, object, object],
) -> None:
    client, _, _ = auth_client

    assert client.get("/api/monitor/targets").status_code == 401
    assert client.get("/api/monitor/events").status_code == 401


def test_operator_can_create_list_and_queue_a_loopback_http_target(
    auth_client: tuple[TestClient, Engine, object],
) -> None:
    client, engine, token_file = auth_client
    authenticate_client(client, token_file)

    created = client.post(
        "/api/monitor/targets",
        json={
            "name": "本地健康检查",
            "kind": "http",
            "endpoint": "http://127.0.0.1:8000/health",
            "interval_seconds": 60,
            "timeout_seconds": 5,
            "failure_threshold": 3,
            "recovery_threshold": 2,
        },
    )

    assert created.status_code == 201
    target = created.json()
    assert target["kind"] == "http"
    assert target["health"] == TargetHealth.UNKNOWN.value
    assert target["endpoint"] == "http://127.0.0.1:8000/health"

    listed = client.get("/api/monitor/targets")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [target["id"]]

    queued = client.post(f"/api/monitor/targets/{target['id']}/probe")
    assert queued.status_code == 202
    assert queued.json()["status"] == TaskStatus.QUEUED.value
    with Session(engine) as session:
        task = session.get(ControlTask, UUID(queued.json()["task_id"]))
        assert task is not None
        assert task.kind == TaskKind.CONTROL
        assert task.capability == "monitor.http"
        assert task.payload == {
            "task_type": "monitor.http",
            "target_id": target["id"],
            "endpoint": "http://127.0.0.1:8000/health",
            "timeout_seconds": 5,
        }


def test_monitoring_routes_reject_unsafe_targets_with_chinese_error_contract(
    auth_client: tuple[TestClient, Engine, object],
) -> None:
    client, _, token_file = auth_client
    authenticate_client(client, token_file)

    response = client.post(
        "/api/monitor/targets",
        json={
            "name": "公网地址",
            "kind": "http",
            "endpoint": "https://example.com/health",
            "interval_seconds": 60,
            "timeout_seconds": 5,
            "failure_threshold": 3,
            "recovery_threshold": 2,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_target"
    assert response.json()["error"]["message"]


def test_scheduler_discovers_only_due_enabled_monitoring_targets(
    auth_client: tuple[TestClient, Engine, object],
) -> None:
    _, engine, _ = auth_client
    with Session(engine) as session:
        session.add_all(
            [
                MonitorTarget(
                    name="到期目标",
                    kind=TargetKind.HTTP,
                    endpoint="http://127.0.0.1:8000/health",
                    next_probe_at=utc_now() - timedelta(seconds=1),
                ),
                MonitorTarget(
                    name="未到期目标",
                    kind=TargetKind.HTTP,
                    endpoint="http://127.0.0.1:8000/ready",
                    next_probe_at=utc_now() + timedelta(minutes=5),
                ),
                MonitorTarget(
                    name="已禁用目标",
                    kind=TargetKind.HTTP,
                    endpoint="http://127.0.0.1:8000/disabled",
                    enabled=False,
                    next_probe_at=utc_now() - timedelta(seconds=1),
                ),
            ]
        )
        session.commit()

        due = discover_due_tasks(session, now=datetime.now(UTC))

    assert len(due) == 1
    assert due[0]["capability"] == "monitor.http"
    payload = due[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["task_type"] == "monitor.http"


def test_native_worker_completion_updates_target_and_observation(
    auth_client: tuple[TestClient, Engine, object],
) -> None:
    client, engine, token_file = auth_client
    authenticate_client(client, token_file)
    created = client.post(
        "/api/monitor/targets",
        json={
            "name": "需要探测的 API",
            "kind": "http",
            "endpoint": "http://127.0.0.1:8000/health",
            "interval_seconds": 60,
            "timeout_seconds": 5,
            "failure_threshold": 1,
            "recovery_threshold": 1,
        }
    ).json()
    task = client.post(f"/api/monitor/targets/{created['id']}/probe").json()

    enrollment_token = "monitor-worker-enrollment"
    with Session(engine) as session:
        session.add(
            ClientToken(
                name="monitor-worker-enrollment",
                token_digest=digest_secret(enrollment_token),
                scopes=["worker:enroll"],
            )
        )
        session.commit()

    registered = client.post(
        "/api/v1/worker/register",
        headers={"Authorization": f"Bearer {enrollment_token}"},
        json={
            "name": "monitor-worker",
            "version": "0.1.0",
            "protocol_version": PROTOCOL_VERSION,
            "capabilities": ["monitor.http"],
        },
    )
    assert registered.status_code == 201
    worker_headers = {"Authorization": f"Bearer {registered.json()['token']}"}
    claim = client.post(
        "/api/v1/worker/claim",
        headers=worker_headers,
        json={"protocol_version": PROTOCOL_VERSION, "capabilities": ["monitor.http"]},
    )
    assert claim.status_code == 200
    grant = claim.json()
    assert grant["task_id"] == task["task_id"]
    started = client.post(
        f"/api/v1/worker/tasks/{task['task_id']}/start",
        headers=worker_headers,
        json={"protocol_version": PROTOCOL_VERSION, "request_digest": grant["request_digest"]},
    )
    assert started.status_code == 204
    completed = client.post(
        f"/api/v1/worker/tasks/{task['task_id']}/complete",
        headers=worker_headers,
        json={
            "protocol_version": PROTOCOL_VERSION,
            "request_digest": grant["request_digest"],
            "result": {"status": "failed", "detail": "HTTP 503", "latency_ms": 20},
        },
    )

    assert completed.status_code == 200
    with Session(engine) as session:
        target = session.get(MonitorTarget, UUID(created["id"]))
        assert target is not None
        assert target.health == TargetHealth.DOWN.value
        assert target.last_probe_status == "failed"
        assert target.last_latency_ms == 20
        monitor_task = session.get(ControlTask, UUID(task["task_id"]))
        assert monitor_task is not None
        assert monitor_task.status == TaskStatus.SUCCEEDED
        assert session.exec(
            select(WorkerRegistration).where(WorkerRegistration.name == "monitor-worker")
        ).first() is not None
