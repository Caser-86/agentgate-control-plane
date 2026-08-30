import asyncio
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import create_db_and_tables, get_engine, seed_demo_state
from app.main import app
from app.repositories import RunRepository
from app.services.events import EventBroker


@pytest.mark.asyncio
async def test_subscriber_receives_events_for_its_run_only() -> None:
    broker = EventBroker(queue_size=2)
    first_run = uuid4()
    second_run = uuid4()
    stream = broker.subscribe(first_run)
    task = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)

    await broker.publish(second_run, "run.updated", {"status": "running"})
    await broker.publish(first_run, "run.updated", {"status": "waiting_approval"})
    event = await asyncio.wait_for(task, timeout=1)

    assert event.run_id == first_run
    assert event.event_type == "run.updated"
    await stream.aclose()


@pytest.mark.asyncio
async def test_slow_subscriber_does_not_block_publish() -> None:
    broker = EventBroker(queue_size=1)
    run_id = uuid4()
    stream = broker.subscribe(run_id)
    task = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)

    await asyncio.wait_for(
        broker.publish(run_id, "run.updated", {"status": "one"}), timeout=1
    )
    await asyncio.wait_for(
        broker.publish(run_id, "run.updated", {"status": "two"}), timeout=1
    )
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await stream.aclose()


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue() -> None:
    broker = EventBroker()
    run_id = uuid4()
    stream = broker.subscribe(run_id)
    task = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)
    assert broker.subscriber_count(run_id) == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await stream.aclose()
    assert broker.subscriber_count(run_id) == 0


@pytest.mark.asyncio
async def test_http_stream_cleans_up_when_client_disconnects() -> None:
    from app.api.runs import stream_events

    broker = EventBroker()
    run_id = uuid4()
    stream = stream_events(run_id, broker)
    task = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert broker.subscriber_count(run_id) == 0


def test_sse_frame_shape() -> None:
    from app.api.runs import format_sse

    frame = format_sse(7, "run.updated", {"status": "running"})

    assert "id: 7\n" in frame
    assert "event: run.updated\n" in frame
    assert f"data: {json.dumps({'status': 'running'})}\n\n" in frame


def test_http_sse_stream_emits_event_frame(monkeypatch) -> None:
    engine = get_engine()
    create_db_and_tables(engine)
    with Session(engine) as session:
        seed_demo_state(session)
        run = RunRepository(session).create("Inspect payments-api", "mock", "mock")
        run_id = run.id

    async def finite_stream(run_id):
        del run_id
        yield "id: 7\nevent: run.updated\ndata: {\"status\": \"running\"}\n\n"

    from app.api import runs as runs_api

    monkeypatch.setattr(runs_api, "stream_events", finite_stream)
    response = TestClient(app).get(f"/api/runs/{run_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: run.updated" in response.text
    assert 'data: {"status": "running"}' in response.text
