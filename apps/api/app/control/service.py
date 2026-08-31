from uuid import UUID

from sqlmodel import Session

from app.control.repositories import append_outbox_event


def commit_with_outbox(
    session: Session, *, event_type: str, resource_type: str, resource_id: UUID,
    payload: dict[str, object],
) -> None:
    """Commit the current domain mutation and its notification atomically."""
    append_outbox_event(
        session, event_type=event_type, resource_type=resource_type, resource_id=resource_id,
        payload=payload,
    )
    session.commit()
