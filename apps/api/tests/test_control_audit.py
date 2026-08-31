import json
from uuid import uuid4

from sqlmodel import Session

from app.control.repositories import read_outbox_after
from app.db import create_db_and_tables, create_db_engine
from app.repositories import AuditRepository
from app.services.audit import AuditService


def test_generic_audit_event_keeps_resource_context_and_redacts_payload() -> None:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    resource_id = uuid4()
    with Session(engine) as session:
        event = AuditService(AuditRepository(session)).append(
            event_type="worker.registered",
            actor="operator",
            payload={"token": "fake-secret", "name": "local-worker"},
            resource_type="worker",
            resource_id=resource_id,
        )
        events = list(read_outbox_after(session, cursor=0, limit=10))

        assert event.run_id is None
        assert event.resource_type == "worker"
        assert event.resource_id == resource_id
        assert json.loads(event.payload_json)["token"] == "***REDACTED***"
        assert events[0].event_type == "worker.registered"
