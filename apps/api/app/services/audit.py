import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

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
        run_id: UUID,
        event_type: str,
        actor: str,
        payload: Mapping[str, Any],
        action_id: UUID | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            run_id=run_id,
            action_id=action_id,
            event_type=event_type,
            actor=actor,
            payload_json=json.dumps(redact(payload), ensure_ascii=False, default=str),
            created_at=datetime.now(UTC),
        )
        return self.repository.append(event)
