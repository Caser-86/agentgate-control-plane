import json
from uuid import uuid4

from sqlmodel import Session

from app.db import create_db_and_tables, create_db_engine
from app.repositories import AuditRepository, RunRepository
from app.services.audit import AuditService, redact


def test_redact_secrets_recursively() -> None:
    payload = {
        "authorization": "credential-placeholder",
        "nested": {"api_key": "secret", "safe": "visible"},
        "items": [{"password": "p"}, {"token": "t"}],
    }

    assert redact(payload) == {
        "authorization": "***REDACTED***",
        "nested": {"api_key": "***REDACTED***", "safe": "visible"},
        "items": [{"password": "***REDACTED***"}, {"token": "***REDACTED***"}],
    }


def test_audit_service_serializes_only_redacted_payload() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as session:
        run = RunRepository(session).create("Inspect payments", "mock", "mock")
        event = AuditService(AuditRepository(session)).append(
            run_id=run.id,
            event_type="tool.proposed",
            actor="agent",
            payload={"api_key": "secret", "nested": {"safe": "visible"}},
            action_id=uuid4(),
        )

        assert json.loads(event.payload_json) == {
            "api_key": "***REDACTED***",
            "nested": {"safe": "visible"},
        }
