from app.control.models import OutboxEvent
from app.services.outbox import format_outbox_sse


def event_to_sse(event: OutboxEvent) -> str:
    """Compatibility serializer for callers migrating from the in-memory broker."""
    return format_outbox_sse(event)
