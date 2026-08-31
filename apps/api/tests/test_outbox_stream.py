from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Session

from app.control.models import OutboxEvent
from app.control.repositories import append_outbox_event
from app.db import create_db_and_tables, create_db_engine
from app.models import RunStatus
from app.repositories import RunRepository
from app.services.outbox import read_events_after


def test_two_readers_receive_the_same_ordered_persisted_events() -> None:
    from app.services.outbox import read_events_after

    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    first_run, second_run = uuid4(), uuid4()
    with Session(engine) as writer:
        first = append_outbox_event(
            writer,
            event_type="run.updated",
            resource_type="run",
            resource_id=first_run,
            payload={"status": "queued"},
        )
        append_outbox_event(
            writer,
            event_type="run.updated",
            resource_type="run",
            resource_id=second_run,
            payload={"status": "running"},
        )
        third = append_outbox_event(
            writer,
            event_type="run.updated",
            resource_type="run",
            resource_id=first_run,
            payload={"status": "completed"},
        )
        writer.commit()
        first_sequence = first.sequence
        third_sequence = third.sequence

    with Session(engine) as reader_a, Session(engine) as reader_b:
        ids_a = [
            event.sequence
            for event in read_events_after(reader_a, cursor=0, resource_id=None, limit=10)
        ]
        ids_b = [
            event.sequence
            for event in read_events_after(reader_b, cursor=0, resource_id=None, limit=10)
        ]
        filtered = read_events_after(
            reader_a, cursor=first_sequence or 0, resource_id=first_run, limit=10
        )

    assert ids_a == ids_b == [first_sequence, (first_sequence or 0) + 1, third_sequence]
    assert [event.sequence for event in filtered] == [third_sequence]


def test_outbox_relay_retries_unacknowledged_event_after_restart() -> None:
    from app.services.outbox import OutboxRelay

    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    run_id = uuid4()
    with Session(engine) as session:
        event = append_outbox_event(
            session,
            event_type="run.updated",
            resource_type="run",
            resource_id=run_id,
            payload={"status": "running"},
        )
        session.commit()
        sequence = event.sequence

    attempted: list[int] = []

    def fails_once(delivered: OutboxEvent) -> None:
        attempted.append(delivered.sequence or 0)
        raise RuntimeError("temporary downstream failure")

    with Session(engine) as session:
        assert OutboxRelay(session, fails_once).relay_once() == 0
        persisted = session.get(OutboxEvent, sequence)
        assert persisted is not None
        assert persisted.published_at is None

    with Session(engine) as session:
        assert (
            OutboxRelay(
                session, lambda delivered: attempted.append(delivered.sequence or 0)
            ).relay_once()
            == 1
        )
        persisted = session.get(OutboxEvent, sequence)
        assert persisted is not None
        first_ack = persisted.published_at
        assert first_ack is not None
        OutboxRelay(session, lambda _: None).acknowledge(persisted)
        session.refresh(persisted)

    assert attempted == [sequence, sequence]
    assert persisted.published_at == first_ack


def test_sse_payload_is_redacted_and_bounded() -> None:
    from app.services.outbox import format_outbox_sse

    event = OutboxEvent(
        sequence=9,
        event_type="adapter.event.proposed",
        resource_type="adapter_event",
        resource_id=uuid4(),
        payload={"token": "not-for-clients", "body": "x" * 20_000},
        created_at=datetime.now(UTC),
    )

    frame = format_outbox_sse(event)

    assert "not-for-clients" not in frame
    assert "***REDACTED***" in frame
    assert len(frame.encode("utf-8")) <= 8192


def test_run_state_and_outbox_event_rollback_together() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        run = RunRepository(session).create("inspect", "mock", "mock")
        changed = RunRepository(session).set_status(
            run.id, {RunStatus.QUEUED}, RunStatus.RUNNING, commit=False
        )
        append_outbox_event(
            session,
            event_type="run.updated",
            resource_type="run",
            resource_id=run.id,
            payload={"status": "running"},
        )
        session.rollback()

        session.refresh(run)
        events = read_events_after(session, cursor=0, resource_id=run.id, limit=10)

    assert changed
    assert run.status == RunStatus.QUEUED
    assert events == []
