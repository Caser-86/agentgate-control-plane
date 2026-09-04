from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.dependencies import ClientIdentity
from app.config import Settings
from app.control.enums import TaskKind, TaskStatus
from app.control.models import ControlTask, OutboxEvent
from app.db import create_db_and_tables, create_db_engine, seed_example_state
from app.models import AgentRun
from app.services.runs import RunService
from tests.conftest import authenticate_client


def _tasks(session: Session, run_id: UUID) -> list[ControlTask]:
    return list(
        session.exec(
            select(ControlTask).where(
                ControlTask.kind == TaskKind.AGENT_RUN,
                ControlTask.run_id == run_id,
            )
        ).all()
    )


def test_create_run_returns_queued_and_enqueues_one_resume_task(
    auth_client: tuple[TestClient, object, object],
) -> None:
    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_example_state(session)
    authenticate_client(client, token_file)

    response = client.post("/api/runs", json={"user_request": "inspect service health"})

    assert response.status_code == 202
    run_id = UUID(response.json()["id"])
    with Session(engine) as session:
        tasks = _tasks(session, run_id)
    assert len(tasks) == 1
    assert tasks[0].status == TaskStatus.QUEUED
    queued = client.get(f"/api/runs/{run_id}/tasks")
    assert queued.status_code == 200
    assert queued.json()[0]["status"] == "queued"


def test_create_run_persists_initial_audit_and_sse_event_with_queued_task(
    auth_client: tuple[TestClient, object, object],
) -> None:
    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_example_state(session)
    authenticate_client(client, token_file)

    response = client.post("/api/runs", json={"user_request": "inspect service health"})

    run_id = UUID(response.json()["id"])
    with Session(engine) as session:
        events = list(
            session.exec(
                select(OutboxEvent).where(OutboxEvent.resource_id == run_id)
            ).all()
        )
        tasks = _tasks(session, run_id)
    assert len(tasks) == 1
    assert any(event.event_type == "run.created" for event in events)
    assert any(event.event_type == "task.queued" for event in events)
    with client.stream("GET", f"/api/runs/{run_id}/events?after=0&limit=2") as stream:
        body = "\n".join(stream.iter_lines())
    assert "event: task.queued" in body


def test_create_run_does_not_use_fastapi_background_tasks(
    auth_client: tuple[TestClient, object, object], monkeypatch
) -> None:
    from fastapi import BackgroundTasks

    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_example_state(session)
    authenticate_client(client, token_file)

    def background_task_is_forbidden(*_: object, **__: object) -> None:
        raise AssertionError("run continuation must be durable")

    monkeypatch.setattr(BackgroundTasks, "add_task", background_task_is_forbidden)

    response = client.post("/api/runs", json={"user_request": "inspect service health"})

    assert response.status_code == 202


def test_create_run_rolls_back_run_and_outbox_when_enqueue_fails(monkeypatch) -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        service = RunService(session, Settings())

        def reject_enqueue(*_: object, **__: object) -> ControlTask:
            raise RuntimeError("queue unavailable")

        monkeypatch.setattr("app.services.runs.enqueue_task", reject_enqueue)

        try:
            service.create("inspect service health", ClientIdentity("test", frozenset()))
        except RuntimeError:
            pass
        else:
            raise AssertionError("enqueue failure must abort run creation")

        assert session.exec(select(AgentRun)).all() == []
        assert session.exec(select(OutboxEvent)).all() == []
