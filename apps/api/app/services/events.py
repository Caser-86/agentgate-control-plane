import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID


@dataclass(frozen=True)
class RunEvent:
    id: int
    run_id: UUID
    event_type: str
    payload: dict[str, object]
    created_at: datetime


class EventBroker:
    """Single-process event delivery for the local demo; production needs a durable stream."""

    def __init__(self, queue_size: int = 100) -> None:
        self.queue_size = queue_size
        self._next_id = 0
        self._next_subscriber = 0
        self._subscribers: dict[
            UUID, dict[int, tuple[asyncio.AbstractEventLoop, asyncio.Queue[RunEvent]]]
        ] = {}

    async def publish(
        self, run_id: UUID, event_type: str, payload: dict[str, object]
    ) -> RunEvent:
        self._next_id += 1
        event = RunEvent(self._next_id, run_id, event_type, payload, datetime.now(UTC))
        for loop, queue in self._subscribers.get(run_id, {}).values():
            loop.call_soon_threadsafe(self._enqueue, queue, event)
        return event

    async def subscribe(self, run_id: UUID) -> AsyncGenerator[RunEvent, None]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[RunEvent] = asyncio.Queue(maxsize=self.queue_size)
        self._next_subscriber += 1
        subscriber_id = self._next_subscriber
        self._subscribers.setdefault(run_id, {})[subscriber_id] = (loop, queue)
        try:
            while True:
                yield await queue.get()
        finally:
            subscribers = self._subscribers.get(run_id, {})
            subscribers.pop(subscriber_id, None)
            if not subscribers:
                self._subscribers.pop(run_id, None)

    def subscriber_count(self, run_id: UUID) -> int:
        return len(self._subscribers.get(run_id, {}))

    def _enqueue(self, queue: asyncio.Queue[RunEvent], event: RunEvent) -> None:
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(event)


event_broker = EventBroker()


def event_to_sse(event: RunEvent) -> str:
    return (
        f"id: {event.id}\n"
        f"event: {event.event_type}\n"
        f"data: {json.dumps(event.payload, ensure_ascii=False, default=str)}\n\n"
    )
