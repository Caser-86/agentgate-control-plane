from uuid import uuid4

from sqlmodel import Session

from app.control.repositories import append_outbox_event, read_outbox_after
from app.db import create_db_and_tables, create_db_engine


def test_outbox_cursor_is_monotonic() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        append_outbox_event(
            session,
            event_type="task.updated",
            resource_type="task",
            resource_id=uuid4(),
            payload={},
        )
        append_outbox_event(
            session,
            event_type="task.updated",
            resource_type="task",
            resource_id=uuid4(),
            payload={},
        )
        events = list(read_outbox_after(session, cursor=0, limit=10))

        assert [event.sequence for event in events] == sorted(event.sequence for event in events)
        assert events[0].sequence > 0
