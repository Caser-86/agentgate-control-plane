import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.db import create_db_and_tables, create_db_engine, seed_demo_state
from app.models import ActionStatus, AgentRun, PolicyDecision, RiskLevel, ServiceState, ToolAction
from app.repositories import AuditRepository, RunRepository
from app.services.executor import ExecutionNotAllowedError, ToolExecutor
from app.tools.operations import ServiceArgs
from app.tools.registry import RegisteredTool, ToolRegistry


@pytest.fixture
def session() -> Session:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as db_session:
        seed_demo_state(db_session)
        yield db_session


def add_action(
    session: Session,
    run: AgentRun,
    name: str,
    arguments: dict[str, object],
    decision: PolicyDecision,
    status: ActionStatus,
) -> ToolAction:
    action = ToolAction(
        run_id=run.id,
        tool_call_id=str(uuid4()),
        tool_name=name,
        risk_level=RiskLevel.MEDIUM if name == "restart_service" else RiskLevel.LOW,
        policy_decision=decision,
        status=status,
        arguments_json=json.dumps(arguments),
        reason="test action",
        idempotency_key=f"{run.id}:{uuid4()}",
        created_at=datetime.now(UTC),
    )
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


def make_executor(session: Session, registry: ToolRegistry | None = None) -> ToolExecutor:
    return ToolExecutor(
        session,
        registry=registry or ToolRegistry(),
        audit=AuditRepository(session),
        timeout_seconds=1,
    )


@pytest.mark.asyncio
async def test_read_tool_auto_executes_and_is_audited(session: Session) -> None:
    run = RunRepository(session).create("Inspect payments", "mock", "mock")
    action = add_action(
        session,
        run,
        "get_service_health",
        {"service": "payments-api"},
        PolicyDecision.AUTO_APPROVE,
        ActionStatus.AUTO_APPROVED,
    )

    saved = await make_executor(session).execute(action.id)

    assert saved.status == ActionStatus.SUCCEEDED
    assert json.loads(saved.result_json or "{}") == {
        "service": "payments-api",
        "health": "degraded",
        "restart_count": 0,
    }
    assert [event.event_type for event in AuditRepository(session).list(run.id)] == [
        "tool.started",
        "tool.succeeded",
    ]


@pytest.mark.asyncio
async def test_restart_requires_approved_state(session: Session) -> None:
    run = RunRepository(session).create("Restart payments", "mock", "mock")
    action = add_action(
        session,
        run,
        "restart_service",
        {"service": "payments-api", "reason": "recover the degraded service"},
        PolicyDecision.REQUIRE_APPROVAL,
        ActionStatus.PENDING_APPROVAL,
    )

    with pytest.raises(ExecutionNotAllowedError):
        await make_executor(session).execute(action.id)


@pytest.mark.asyncio
async def test_denied_action_never_invokes_handler(session: Session) -> None:
    run = RunRepository(session).create("Rotate key", "mock", "mock")
    action = add_action(
        session,
        run,
        "rotate_api_key",
        {"service": "payments-api"},
        PolicyDecision.DENY,
        ActionStatus.DENIED,
    )

    with pytest.raises(ExecutionNotAllowedError):
        await make_executor(session).execute(action.id)

    assert session.get(ServiceState, "payments-api").restart_count == 0


@pytest.mark.asyncio
async def test_duplicate_execution_returns_saved_result_without_second_restart(
    session: Session,
) -> None:
    run = RunRepository(session).create("Restart payments", "mock", "mock")
    action = add_action(
        session,
        run,
        "restart_service",
        {"service": "payments-api", "reason": "recover the degraded service"},
        PolicyDecision.REQUIRE_APPROVAL,
        ActionStatus.APPROVED,
    )
    executor = make_executor(session)

    first = await executor.execute(action.id)
    second = await executor.execute(action.id)

    assert first.result_json == second.result_json
    assert session.get(ServiceState, "payments-api").restart_count == 1


@pytest.mark.asyncio
async def test_tool_timeout_marks_action_failed(session: Session) -> None:
    async def slow_handler(_: ServiceArgs, __: Session) -> dict[str, object]:
        await asyncio.sleep(0.05)
        return {"ok": True}

    registry = ToolRegistry()
    registered = registry.get("get_service_health")
    registry.replace(
        "get_service_health",
        RegisteredTool(registered.spec, registered.arguments_model, slow_handler),
    )
    run = RunRepository(session).create("Inspect payments", "mock", "mock")
    action = add_action(
        session,
        run,
        "get_service_health",
        {"service": "payments-api"},
        PolicyDecision.AUTO_APPROVE,
        ActionStatus.AUTO_APPROVED,
    )

    saved = await ToolExecutor(
        session,
        registry=registry,
        audit=AuditRepository(session),
        timeout_seconds=0.001,
    ).execute(action.id)

    assert saved.status == ActionStatus.FAILED
    assert "timed out" in (saved.result_json or "")


@pytest.mark.asyncio
async def test_concurrent_execution_claims_action_once(tmp_path) -> None:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'concurrent.db'}")
    create_db_and_tables(engine)
    with Session(engine) as setup_session:
        seed_demo_state(setup_session)
        run = RunRepository(setup_session).create("Restart payments", "mock", "mock")
        run_id = run.id
        action = add_action(
            setup_session,
            run,
            "restart_service",
            {"service": "payments-api", "reason": "recover the degraded service"},
            PolicyDecision.REQUIRE_APPROVAL,
            ActionStatus.APPROVED,
        )

    async def execute_with_new_session():
        with Session(engine) as worker_session:
            return await make_executor(worker_session).execute(action.id)

    results = await asyncio.gather(
        execute_with_new_session(), execute_with_new_session(), return_exceptions=True
    )

    assert all(isinstance(result, ToolAction) for result in results)
    with Session(engine) as check_session:
        assert check_session.get(ServiceState, "payments-api").restart_count == 1
        assert [event.event_type for event in AuditRepository(check_session).list(run_id)].count(
            "tool.succeeded"
        ) == 1
