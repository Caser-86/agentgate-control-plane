from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.db import create_db_and_tables, create_db_engine, seed_example_state
from app.models import (
    ActionStatus,
    AuditEvent,
    PolicyDecision,
    RiskLevel,
    RunStatus,
    ServiceState,
    ToolAction,
)
from app.repositories import ActionRepository, AuditRepository, RunRepository


@pytest.fixture
def session() -> Session:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as db_session:
        seed_example_state(db_session)
        yield db_session


def make_action(run_id: UUID, *, status: ActionStatus = ActionStatus.PROPOSED) -> ToolAction:
    call_id = str(uuid4())
    return ToolAction(
        run_id=run_id,
        tool_call_id=call_id,
        tool_name="get_service_health",
        risk_level=RiskLevel.LOW,
        policy_decision=PolicyDecision.AUTO_APPROVE,
        status=status,
        arguments_json='{"service":"payments-api"}',
        idempotency_key=f"{run_id}:{call_id}",
    )


def test_create_run_defaults_to_queued(session: Session) -> None:
    run = RunRepository(session).create(
        "Inspect payments", provider="mock", model="mock-operations-agent"
    )

    assert run.status == RunStatus.QUEUED
    assert run.step_count == 0
    assert run.conversation_json == "[]"


def test_action_idempotency_key_is_unique(session: Session) -> None:
    run = RunRepository(session).create("Inspect payments", "mock", "mock-operations-agent")
    first = make_action(run.id)
    second = ToolAction(
        id=uuid4(),
        run_id=first.run_id,
        tool_call_id=first.tool_call_id,
        tool_name=first.tool_name,
        risk_level=first.risk_level,
        policy_decision=first.policy_decision,
        status=first.status,
        arguments_json=first.arguments_json,
        idempotency_key=first.idempotency_key,
    )
    session.add(first)
    session.commit()
    session.add(second)

    with pytest.raises(IntegrityError):
        session.commit()


def test_pending_action_can_be_atomically_claimed_once(session: Session) -> None:
    run = RunRepository(session).create("Restart payments", "mock", "mock-operations-agent")
    action = make_action(run.id, status=ActionStatus.PENDING_APPROVAL)
    session.add(action)
    session.commit()

    repository = ActionRepository(session)
    assert repository.transition(action.id, {ActionStatus.PENDING_APPROVAL}, ActionStatus.APPROVED)
    assert not repository.transition(
        action.id, {ActionStatus.PENDING_APPROVAL}, ActionStatus.DENIED
    )


def test_audit_repository_exposes_append_and_list_only(session: Session) -> None:
    run = RunRepository(session).create("Inspect payments", "mock", "mock-operations-agent")
    repository = AuditRepository(session)
    event = repository.append(
        AuditEvent(
            run_id=run.id,
            event_type="run.created",
            actor="user",
            payload_json='{"request":"Inspect payments"}',
            created_at=datetime.now(UTC),
        )
    )

    assert event.id is not None
    assert [item.event_type for item in repository.list(run_id=run.id)] == ["run.created"]
    assert not hasattr(repository, "update")
    assert not hasattr(repository, "delete")


def test_seeded_payments_service_is_degraded(session: Session) -> None:
    service = session.get(ServiceState, "payments-api")

    assert service is not None
    assert service.health == "degraded"
    assert service.restart_count == 0
