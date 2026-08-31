from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.control.repositories import append_outbox_event
from app.db import seed_demo_state
from app.repositories import RunRepository
from tests.conftest import authenticate_client


async def _take(stream: AsyncIterator[str], count: int) -> list[str]:
    frames: list[str] = []
    try:
        for _ in range(count):
            frames.append(await anext(stream))
    finally:
        await stream.aclose()
    return frames


@pytest.mark.asyncio
async def test_run_stream_reconnects_after_last_event_id() -> None:
    from app.db import create_db_and_tables, create_db_engine
    from app.services.outbox import stream_outbox_events

    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    run_id = uuid4()
    with Session(engine) as session:
        for status in ("queued", "running", "completed"):
            append_outbox_event(
                session,
                event_type="run.updated",
                resource_type="run",
                resource_id=run_id,
                payload={"status": status},
            )
        session.commit()

    frames = await _take(
        stream_outbox_events(
            lambda: Session(engine), cursor=2, resource_id=run_id, poll_interval=0.01
        ),
        1,
    )

    assert frames == ['id: 3\nevent: run.updated\ndata: {"status": "completed"}\n\n']


@pytest.mark.asyncio
async def test_idle_stream_emits_a_heartbeat_and_can_be_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db import create_db_and_tables, create_db_engine
    from app.services import outbox as outbox_service
    from app.services.outbox import stream_outbox_events

    monkeypatch.setattr(outbox_service, "HEARTBEAT_SECONDS", 0.01)
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    stream = stream_outbox_events(lambda: Session(engine), cursor=0, resource_id=uuid4())

    assert await anext(stream) == ": heartbeat\n\n"
    await stream.aclose()


def test_sse_cursor_prefers_the_smaller_valid_last_event_id_and_after() -> None:
    from app.services.outbox import effective_cursor

    assert effective_cursor(last_event_id="7", after="3") == 3
    assert effective_cursor(last_event_id="7", after="invalid") == 7
    assert effective_cursor(last_event_id="invalid", after="3") == 3
    assert effective_cursor(last_event_id="-1", after=None) == 0


def test_missing_run_stream_returns_404_without_opening_a_stream(
    monkeypatch: pytest.MonkeyPatch, auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, token_file = auth_client
    from app.api import runs as runs_api

    def stream_was_not_opened(*_: object, **__: object) -> AsyncIterator[str]:
        raise AssertionError("missing run must not open an event stream")

    monkeypatch.setattr(runs_api, "stream_run_events", stream_was_not_opened)
    authenticate_client(client, token_file)

    response = client.get(f"/api/runs/{uuid4()}/events")

    assert response.status_code == 404


def test_http_sse_stream_has_durable_event_headers(
    monkeypatch: pytest.MonkeyPatch, auth_client: tuple[TestClient, object, object]
) -> None:
    client, engine, token_file = auth_client
    with Session(engine) as session:
        seed_demo_state(session)
        run = RunRepository(session).create("Inspect payments-api", "mock", "mock")
        run_id = run.id

    async def finite_stream(*_: object, **__: object) -> AsyncIterator[str]:
        yield 'id: 7\nevent: run.updated\ndata: {"status": "running"}\n\n'

    from app.api import runs as runs_api

    monkeypatch.setattr(runs_api, "stream_run_events", finite_stream)
    authenticate_client(client, token_file)
    response = client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "2"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert "id: 7" in response.text


def test_generic_events_stream_accepts_events_without_run_id(
    monkeypatch: pytest.MonkeyPatch, auth_client: tuple[TestClient, object, object]
) -> None:
    client, _, token_file = auth_client
    from app.api import events as events_api

    async def finite_stream(*_: object, **__: object) -> AsyncIterator[str]:
        yield 'id: 9\nevent: adapter.event.proposed\ndata: {"source": "adapter"}\n\n'

    monkeypatch.setattr(events_api, "stream_events", finite_stream)
    authenticate_client(client, token_file)
    response = client.get("/api/v1/events?after=8")

    assert response.status_code == 200
    assert "event: adapter.event.proposed" in response.text
