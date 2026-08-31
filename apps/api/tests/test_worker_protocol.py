from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.auth.models import ClientToken
from app.auth.security import digest_secret
from app.control.enums import TaskKind, TaskStatus
from app.control.models import ControlTask, WorkerRegistration
from app.control.repositories import enqueue_task

PROTOCOL_VERSION = "1.0"
SELF_CHECK_CAPABILITY = "platform.self_check"


def _issue_enrollment_token(engine: Engine, suffix: str = "") -> str:
    """A regression that removed one-use enrolment would leave a live token behind."""
    raw_token = f"enrollment-token-for-test-only{suffix}"
    with Session(engine) as session:
        session.add(
            ClientToken(
                name="worker-enrollment",
                token_digest=digest_secret(raw_token),
                scopes=["worker:enroll"],
            )
        )
        session.commit()
    return raw_token


def _register_worker(
    client: TestClient, engine: Engine, *, name: str = "local-worker"
) -> dict[str, object]:
    enrollment_token = _issue_enrollment_token(engine, name)
    response = client.post(
        "/api/v1/worker/register",
        headers={"Authorization": f"Bearer {enrollment_token}"},
        json={
            "name": name,
            "version": "0.1.0",
            "protocol_version": PROTOCOL_VERSION,
            "capabilities": [SELF_CHECK_CAPABILITY],
        },
    )
    assert response.status_code == 201
    return response.json()


def _worker_headers(identity: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {identity['token']}"}


def _enqueue_self_check(engine: Engine, idempotency_key: str) -> UUID:
    with Session(engine) as session:
        task = enqueue_task(
            session,
            kind=TaskKind.CONTROL,
            payload={"task_type": SELF_CHECK_CAPABILITY},
            idempotency_key=idempotency_key,
            capability=SELF_CHECK_CAPABILITY,
        )
        session.commit()
        return task.id


def test_register_rejects_invalid_enrollment_token(
    auth_client: tuple[TestClient, Engine, object],
) -> None:
    """Removing enrolment authentication would permit an arbitrary host to register."""
    client, _, _ = auth_client

    response = client.post(
        "/api/v1/worker/register",
        headers={"Authorization": "Bearer invalid-enrollment-token"},
        json={
            "name": "untrusted-worker",
            "version": "0.1.0",
            "protocol_version": PROTOCOL_VERSION,
            "capabilities": [SELF_CHECK_CAPABILITY],
        },
    )

    assert response.status_code == 401


def test_registration_issues_distinct_worker_token_and_consumes_enrollment(
    auth_client: tuple[TestClient, Engine, object],
) -> None:
    """Replacing the worker credential with the enrolment token would defeat one-time enrolment."""
    client, engine, _ = auth_client
    enrollment_token = _issue_enrollment_token(engine)

    response = client.post(
        "/api/v1/worker/register",
        headers={"Authorization": f"Bearer {enrollment_token}"},
        json={
            "name": "local-worker",
            "version": "0.1.0",
            "protocol_version": PROTOCOL_VERSION,
            "capabilities": [SELF_CHECK_CAPABILITY],
        },
    )

    assert response.status_code == 201
    identity = response.json()
    assert identity["token"] != enrollment_token
    with Session(engine) as session:
        registration = session.get(WorkerRegistration, UUID(identity["worker_id"]))
        enrollment = session.exec(
            select(ClientToken).where(ClientToken.token_digest == digest_secret(enrollment_token))
        ).first()
        assert registration is not None
        assert registration.token_digest != identity["token"]
        assert enrollment is not None
        assert enrollment.revoked_at is not None


def test_worker_cannot_claim_without_registered_capability(
    auth_client: tuple[TestClient, Engine, object],
) -> None:
    """Trusting caller-supplied capabilities would let a Worker escalate to host operations."""
    client, engine, _ = auth_client
    identity = _register_worker(client, engine)
    task_id = _enqueue_self_check(engine, "capability-filter")

    response = client.post(
        "/api/v1/worker/claim",
        headers=_worker_headers(identity),
        json={"protocol_version": PROTOCOL_VERSION, "capabilities": ["host.restart"]},
    )

    assert response.status_code == 403
    with Session(engine) as session:
        task = session.get(ControlTask, task_id)
        assert task is not None
        assert task.status == TaskStatus.QUEUED


def test_heartbeat_is_bound_to_registered_worker_and_protocol(
    auth_client: tuple[TestClient, Engine, object],
) -> None:
    """Accepting another protocol or credential would misattribute leases."""
    client, engine, _ = auth_client
    identity = _register_worker(client, engine)

    incompatible = client.post(
        "/api/v1/worker/heartbeat",
        headers=_worker_headers(identity),
        json={"protocol_version": "999.0"},
    )
    accepted = client.post(
        "/api/v1/worker/heartbeat",
        headers=_worker_headers(identity),
        json={"protocol_version": PROTOCOL_VERSION},
    )

    assert incompatible.status_code == 403
    assert accepted.status_code == 204
    with Session(engine) as session:
        worker = session.get(WorkerRegistration, UUID(identity["worker_id"]))
        assert worker is not None
        assert worker.last_heartbeat_at is not None


def test_start_and_complete_require_claim_owner_and_request_digest(
    auth_client: tuple[TestClient, Engine, object],
) -> None:
    """Dropping owner or digest checks would allow a second Worker to execute a leased task."""
    client, engine, _ = auth_client
    owner = _register_worker(client, engine, name="owner")
    contender = _register_worker(client, engine, name="contender")
    task_id = _enqueue_self_check(engine, "lease-owner")
    grant_response = client.post(
        "/api/v1/worker/claim",
        headers=_worker_headers(owner),
        json={"protocol_version": PROTOCOL_VERSION, "capabilities": [SELF_CHECK_CAPABILITY]},
    )
    assert grant_response.status_code == 200
    grant = grant_response.json()

    wrong_owner = client.post(
        f"/api/v1/worker/tasks/{task_id}/start",
        headers=_worker_headers(contender),
        json={"protocol_version": PROTOCOL_VERSION, "request_digest": grant["request_digest"]},
    )
    started = client.post(
        f"/api/v1/worker/tasks/{task_id}/start",
        headers=_worker_headers(owner),
        json={"protocol_version": PROTOCOL_VERSION, "request_digest": grant["request_digest"]},
    )
    wrong_digest = client.post(
        f"/api/v1/worker/tasks/{task_id}/complete",
        headers=_worker_headers(owner),
        json={
            "protocol_version": PROTOCOL_VERSION,
            "request_digest": "0" * 64,
            "result": {"status": "succeeded"},
        },
    )
    completed = client.post(
        f"/api/v1/worker/tasks/{task_id}/complete",
        headers=_worker_headers(owner),
        json={
            "protocol_version": PROTOCOL_VERSION,
            "request_digest": grant["request_digest"],
            "result": {"status": "succeeded"},
        },
    )

    assert wrong_owner.status_code == 403
    assert started.status_code == 204
    assert wrong_digest.status_code == 403
    assert completed.status_code == 200
    with Session(engine) as session:
        task = session.get(ControlTask, task_id)
        assert task is not None
        assert task.status == TaskStatus.SUCCEEDED
        assert task.result == {"status": "succeeded"}


def test_result_report_replays_only_the_identical_completed_result(
    auth_client: tuple[TestClient, Engine, object],
) -> None:
    """Allowing a replay to replace a result would break idempotency and the audit trail."""
    client, engine, _ = auth_client
    identity = _register_worker(client, engine)
    task_id = _enqueue_self_check(engine, "result-replay")
    grant = client.post(
        "/api/v1/worker/claim",
        headers=_worker_headers(identity),
        json={"protocol_version": PROTOCOL_VERSION, "capabilities": [SELF_CHECK_CAPABILITY]},
    ).json()
    started = client.post(
        f"/api/v1/worker/tasks/{task_id}/start",
        headers=_worker_headers(identity),
        json={"protocol_version": PROTOCOL_VERSION, "request_digest": grant["request_digest"]},
    )
    assert started.status_code == 204
    result = {"status": "succeeded", "worker_version": "0.1.0"}
    completed = client.post(
        f"/api/v1/worker/tasks/{task_id}/complete",
        headers=_worker_headers(identity),
        json={
            "protocol_version": PROTOCOL_VERSION,
            "request_digest": grant["request_digest"],
            "result": result,
        },
    )
    replay = client.post(
        f"/api/v1/worker/tasks/{task_id}/report",
        headers=_worker_headers(identity),
        json={
            "protocol_version": PROTOCOL_VERSION,
            "request_digest": grant["request_digest"],
            "result": result,
        },
    )
    altered = client.post(
        f"/api/v1/worker/tasks/{task_id}/report",
        headers=_worker_headers(identity),
        json={
            "protocol_version": PROTOCOL_VERSION,
            "request_digest": grant["request_digest"],
            "result": {"status": "failed"},
        },
    )

    assert completed.status_code == 200
    assert replay.status_code == 200
    assert altered.status_code == 409
