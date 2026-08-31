import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.control.repositories import append_outbox_event
from app.models import AuditEvent
from app.repositories import AuditRepository

REDACTED = "***REDACTED***"
SENSITIVE_KEYS = {"api_key", "authorization", "token", "secret", "password"}


def redact(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: REDACTED
            if isinstance(key, str) and key.lower() in SENSITIVE_KEYS
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


class AuditService:
    def __init__(self, repository: AuditRepository) -> None:
        self.repository = repository

    def append(
        self,
        run_id: UUID | None = None,
        event_type: str = "",
        actor: str = "system",
        payload: Mapping[str, Any] | None = None,
        action_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        commit: bool = True,
    ) -> AuditEvent:
        if resource_type is None:
            resource_type = "action" if action_id is not None else "run"
        if resource_id is None:
            resource_id = action_id or run_id
        if resource_id is None:
            raise ValueError("audit event requires a run/action or generic resource context")
        event = AuditEvent(
            run_id=run_id,
            action_id=action_id,
            resource_type=resource_type,
            resource_id=resource_id,
            event_type=event_type,
            actor=actor,
            payload_json=json.dumps(redact(payload or {}), ensure_ascii=False, default=str),
            created_at=datetime.now(UTC),
        )
        persisted = self.repository.append(event, commit=False)
        append_outbox_event(
            self.repository.session,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            payload={"audit_event_id": str(persisted.id)},
        )
        if commit:
            self.repository.session.commit()
            self.repository.session.refresh(persisted)
        return persisted
