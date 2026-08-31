import asyncio
import json

import pytest
from sqlmodel import Session

from app.db import create_db_and_tables, create_db_engine, seed_demo_state
from app.llm.mock import MockLLMProvider
from app.models import ActionStatus, AgentRun, RunStatus, ServiceState
from app.processes.control_worker import ControlWorker
from app.repositories import ActionRepository, AuditRepository
from app.services.agent_loop import AgentRunner
from app.services.approvals import ApprovalConflictError, ApprovalService


@pytest.fixture
def session() -> Session:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as db_session:
        seed_demo_state(db_session)
        yield db_session


async def waiting_runner(session: Session) -> tuple[AgentRunner, str]:
    runner = AgentRunner(session, provider=MockLLMProvider(), run_timeout_seconds=5)
    run_id = await runner.start_run(
        "Investigate payments-api and restore it safely. Do not rotate credentials."
    )
    return runner, str(run_id)


@pytest.mark.asyncio
async def test_approve_executes_once_and_resumes_run(session: Session) -> None:
    runner, run_id_text = await waiting_runner(session)
    from uuid import UUID

    run_id = UUID(run_id_text)
    action = ActionRepository(session).list_for_run(run_id)[-1]

    saved = await ApprovalService(session).approve(
        action.id, actor="alice", note="Approved after checking the impact."
    )

    assert saved.status == ActionStatus.APPROVED
    assert await asyncio.to_thread(ControlWorker(session.get_bind()).run_once) == 1
    session.expire_all()
    assert session.get(AgentRun, run_id).status == RunStatus.COMPLETED
    assert session.get(ServiceState, "payments-api").restart_count == 1
    approval_events = [
        event
        for event in AuditRepository(session).list(run_id)
        if event.event_type == "approval.approved"
    ]
    assert approval_events[0].actor == "alice"
    assert "arguments_sha256" in json.loads(approval_events[0].payload_json)


@pytest.mark.asyncio
async def test_deny_records_denial_without_handler_and_resumes(session: Session) -> None:
    runner, run_id_text = await waiting_runner(session)
    from uuid import UUID

    run_id = UUID(run_id_text)
    action = ActionRepository(session).list_for_run(run_id)[-1]

    saved = await ApprovalService(session).deny(
        action.id, actor="bob", note="No restart during the maintenance window."
    )

    assert saved.status == ActionStatus.DENIED
    assert await asyncio.to_thread(ControlWorker(session.get_bind()).run_once) == 1
    session.expire_all()
    assert json.loads(saved.result_json or "{}")["denied"] is True
    assert session.get(ServiceState, "payments-api").restart_count == 0
    assert session.get(AgentRun, run_id).status == RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_duplicate_approval_conflicts_without_second_execution(session: Session) -> None:
    runner, run_id_text = await waiting_runner(session)
    from uuid import UUID

    run_id = UUID(run_id_text)
    action = ActionRepository(session).list_for_run(run_id)[-1]
    service = ApprovalService(session)

    await service.approve(action.id, actor="alice")
    with pytest.raises(ApprovalConflictError):
        await service.approve(action.id, actor="alice")

    assert await asyncio.to_thread(ControlWorker(session.get_bind()).run_once) == 1
    session.expire_all()
    assert session.get(ServiceState, "payments-api").restart_count == 1


@pytest.mark.asyncio
async def test_concurrent_approval_decisions_have_one_winner(session: Session) -> None:
    runner, run_id_text = await waiting_runner(session)
    from uuid import UUID

    run_id = UUID(run_id_text)
    action = ActionRepository(session).list_for_run(run_id)[-1]
    service = ApprovalService(session)

    results = await asyncio.gather(
        service.approve(action.id, actor="alice"),
        service.deny(action.id, actor="bob"),
        return_exceptions=True,
    )

    assert sum(isinstance(result, ApprovalConflictError) for result in results) == 1
    assert sum(not isinstance(result, Exception) for result in results) == 1
