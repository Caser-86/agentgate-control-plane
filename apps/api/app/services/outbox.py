import asyncio
import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlmodel import Session, select

from app.control.models import OutboxEvent
from app.services.audit import redact

MAX_EVENT_FRAME_BYTES = 8192
MAX_EVENT_BATCH = 100
HEARTBEAT_SECONDS = 15.0
POLL_INTERVAL_SECONDS = 1.0


def read_events_after(
    session: Session, *, cursor: int, resource_id: UUID | None, limit: int
) -> list[OutboxEvent]:
    statement = (
        select(OutboxEvent)
        .where(cast(Any, OutboxEvent.sequence) > max(cursor, 0))
        .order_by(cast(Any, OutboxEvent.sequence))
        .limit(min(max(limit, 1), MAX_EVENT_BATCH))
    )
    if resource_id is not None:
        statement = statement.where(cast(Any, OutboxEvent.resource_id) == resource_id)
    return list(session.exec(statement).all())


def _valid_cursor(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def effective_cursor(*, last_event_id: str | None, after: str | None) -> int:
    cursors = [
        cursor
        for cursor in (_valid_cursor(last_event_id), _valid_cursor(after))
        if cursor is not None
    ]
    return min(cursors) if cursors else 0


def _preview(value: object, depth: int = 0) -> object:
    if depth >= 4:
        return "…"
    if isinstance(value, dict):
        return {str(key): _preview(item, depth + 1) for key, item in list(value.items())[:20]}
    if isinstance(value, list):
        return [_preview(item, depth + 1) for item in value[:20]]
    if isinstance(value, str):
        return f"{value[:256]}…" if len(value) > 256 else value
    return value


def format_outbox_sse(event: OutboxEvent) -> str:
    payload = redact(event.payload)
    data = json.dumps(payload, ensure_ascii=False, default=str)
    sequence = event.sequence or 0
    frame = f"id: {sequence}\nevent: {event.event_type}\ndata: {data}\n\n"
    if len(frame.encode("utf-8")) <= MAX_EVENT_FRAME_BYTES:
        return frame
    bounded = {"truncated": True, "payload": _preview(payload)}
    data = json.dumps(bounded, ensure_ascii=False, default=str)
    frame = f"id: {sequence}\nevent: {event.event_type}\ndata: {data}\n\n"
    if len(frame.encode("utf-8")) <= MAX_EVENT_FRAME_BYTES:
        return frame
    return f'id: {sequence}\nevent: {event.event_type}\ndata: {{"truncated":true}}\n\n'


async def stream_outbox_events(
    session_factory: Callable[[], Session],
    *,
    cursor: int,
    resource_id: UUID | None,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    max_events: int | None = None,
) -> AsyncIterator[str]:
    current_cursor = max(cursor, 0)
    delivered = 0
    loop = asyncio.get_running_loop()
    next_heartbeat = loop.time() + HEARTBEAT_SECONDS
    while True:
        with session_factory() as session:
            events = read_events_after(
                session, cursor=current_cursor, resource_id=resource_id, limit=MAX_EVENT_BATCH
            )
        if events:
            for event in events:
                if event.sequence is None:
                    continue
                current_cursor = event.sequence
                yield format_outbox_sse(event)
                delivered += 1
                if max_events is not None and delivered >= max_events:
                    return
            continue
        now = loop.time()
        if now >= next_heartbeat:
            yield ": heartbeat\n\n"
            next_heartbeat = now + HEARTBEAT_SECONDS
        await asyncio.sleep(min(max(poll_interval, 0.01), max(next_heartbeat - now, 0.01)))


class OutboxRelay:
    """At-least-once relay: only an acknowledged delivery is marked published."""

    def __init__(self, session: Session, deliver: Callable[[OutboxEvent], None]) -> None:
        self.session = session
        self.deliver = deliver

    def acknowledge(self, event: OutboxEvent) -> None:
        if event.published_at is None:
            event.published_at = datetime.now(UTC)
            self.session.add(event)
            self.session.commit()

    def relay_once(self, limit: int = MAX_EVENT_BATCH) -> int:
        pending = list(
            self.session.exec(
                select(OutboxEvent)
                .where(cast(Any, OutboxEvent.published_at).is_(None))
                .order_by(cast(Any, OutboxEvent.sequence))
                .limit(min(max(limit, 1), MAX_EVENT_BATCH))
            ).all()
        )
        delivered = 0
        for event in pending:
            try:
                self.deliver(event)
            except Exception:
                self.session.rollback()
                break
            self.acknowledge(event)
            delivered += 1
        return delivered
