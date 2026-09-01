from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.control.enums import TaskKind, TaskStatus
from app.control.models import ControlTask
from app.models import utc_now
from tests.conftest import authenticate_client


def test_platform_endpoints_require_operator_session(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, _ = auth_client
    assert client.get("/api/platform/health").status_code == 401
    assert client.get("/api/platform/self-check").status_code == 401


def test_platform_health_distinguishes_worker_and_target_health(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, token_file = auth_client
    authenticate_client(client, token_file)

    response = client.get("/api/platform/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body["checks"]) >= {"api", "database", "queue", "outbox", "worker"}
    for check in body["checks"].values():
        assert set(check) >= {"status", "code", "message_zh", "observed_at", "details"}
        assert len(check["details"]) <= 10
        assert "token" not in str(check).lower()


def test_platform_self_check_exposes_bounded_operational_metadata_without_secrets(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, token_file = auth_client
    authenticate_client(client, token_file)

    response = client.get("/api/platform/self-check")

    assert response.status_code == 200
    body = response.json()
    assert {
        "migration_head",
        "queue_latency_ms",
        "worker_heartbeat_age_seconds",
        "provider",
    } <= set(body)
    assert body["provider"]["name"]
    assert "api_key" not in response.text
    assert "bootstrap" not in response.text.lower()


def test_platform_self_check_reports_queue_latency_with_a_queued_control_task(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, engine, token_file = auth_client
    authenticate_client(client, token_file)
    with Session(engine) as session:
        session.add(
            ControlTask(
                kind=TaskKind.CONTROL,
                status=TaskStatus.QUEUED,
                capability="platform.self_check",
                idempotency_key="platform-self-check-queued-regression",
                available_at=utc_now(),
            )
        )
        session.commit()

    response = client.get("/api/platform/self-check")

    assert response.status_code == 200
    queue_latency_ms = response.json()["queue_latency_ms"]
    assert isinstance(queue_latency_ms, int)
    assert 0 <= queue_latency_ms <= 5_000


def test_platform_self_check_rejects_a_stale_database_revision(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, engine, token_file = auth_client
    authenticate_client(client, token_file)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        connection.execute(
            text("INSERT INTO alembic_version(version_num) VALUES ('0005_worker_protocol')")
        )

    response = client.get("/api/platform/self-check")

    assert response.status_code == 200
    assert response.json()["migration_check"]["code"] == "database_migration_mismatch"
    assert response.json()["migration_check"]["status"] == "error"


def test_platform_self_check_reports_a_missing_database_revision(
    auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, token_file = auth_client
    authenticate_client(client, token_file)

    response = client.get("/api/platform/self-check")

    assert response.status_code == 200
    assert response.json()["migration_check"]["code"] == "database_migration_missing"
