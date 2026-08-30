import json

import pytest
from sqlmodel import Session

from app.db import create_db_and_tables, create_db_engine, seed_demo_state
from app.llm.base import ModelTurn, ToolCall
from app.llm.mock import MockLLMProvider
from app.models import ActionStatus, AgentRun, RunStatus, ServiceState
from app.repositories import ActionRepository, AuditRepository
from app.services.agent_loop import AgentRunner


@pytest.fixture
def session() -> Session:
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as db_session:
        seed_demo_state(db_session)
        yield db_session


def make_runner(session: Session, provider=None, max_steps: int = 8) -> AgentRunner:
    return AgentRunner(
        session,
        provider=provider or MockLLMProvider(),
        max_steps=max_steps,
        run_timeout_seconds=5,
    )


@pytest.mark.asyncio
async def test_healthy_run_completes_without_approval(session: Session) -> None:
    run_id = await make_runner(session).start_run("Inspect orders-api")
    run = session.get(AgentRun, run_id)

    assert run.status == RunStatus.COMPLETED
    assert [action.tool_name for action in ActionRepository(session).list_for_run(run_id)] == [
        "get_service_health"
    ]


@pytest.mark.asyncio
async def test_degraded_run_pauses_before_restart(session: Session) -> None:
    run_id = await make_runner(session).start_run(
        "Investigate payments-api and restore it safely. Do not rotate credentials."
    )
    run = session.get(AgentRun, run_id)
    actions = ActionRepository(session).list_for_run(run_id)

    assert run.status == RunStatus.WAITING_APPROVAL
    assert actions[-1].tool_name == "restart_service"
    assert actions[-1].status == ActionStatus.PENDING_APPROVAL
    assert json.loads(run.conversation_json)
    assert session.get(ServiceState, "payments-api").restart_count == 0


@pytest.mark.asyncio
async def test_high_risk_tool_is_denied_without_execution(session: Session) -> None:
    run_id = await make_runner(session).start_run("Rotate the API key for payments-api.")
    actions = ActionRepository(session).list_for_run(run_id)

    assert session.get(AgentRun, run_id).status == RunStatus.COMPLETED
    assert actions[0].tool_name == "rotate_api_key"
    assert actions[0].status == ActionStatus.DENIED
    assert session.get(ServiceState, "payments-api").restart_count == 0


class UnknownToolProvider:
    async def complete(self, messages, tools) -> ModelTurn:
        if not any(message.get("role") == "tool" for message in messages):
            call = ToolCall("unknown_1", "unknown_tool", {})
            return ModelTurn(
                {"role": "assistant", "content": None, "tool_calls": []}, None, (call,)
            )
        return ModelTurn(
            {"role": "assistant", "content": "Unknown tool was refused."},
            "Unknown tool was refused.",
            (),
        )


@pytest.mark.asyncio
async def test_unknown_tool_fails_closed_and_is_audited(session: Session) -> None:
    run_id = await make_runner(session, UnknownToolProvider()).start_run("Investigate safely")
    actions = ActionRepository(session).list_for_run(run_id)
    events = AuditRepository(session).list(run_id)

    assert actions[0].tool_name == "unknown_tool"
    assert actions[0].status == ActionStatus.DENIED
    assert any(event.event_type == "tool.denied" for event in events)


class InfiniteHealthProvider:
    async def complete(self, messages, tools) -> ModelTurn:
        call = ToolCall("health_1", "get_service_health", {"service": "payments-api"})
        return ModelTurn(
            {"role": "assistant", "content": None, "tool_calls": []}, None, (call,)
        )


@pytest.mark.asyncio
async def test_max_steps_marks_run_failed(session: Session) -> None:
    run_id = await make_runner(session, InfiniteHealthProvider(), max_steps=1).start_run(
        "Inspect forever"
    )

    run = session.get(AgentRun, run_id)
    assert run.status == RunStatus.FAILED
    assert "maximum" in (run.error_message or "")


@pytest.mark.asyncio
async def test_checkpoint_contains_messages_needed_for_resume(session: Session) -> None:
    run_id = await make_runner(session).start_run(
        "Investigate payments-api and restore it safely. Do not rotate credentials."
    )
    run = session.get(AgentRun, run_id)
    messages = json.loads(run.conversation_json)

    assert messages[0]["role"] == "user"
    assert any(message.get("role") == "assistant" for message in messages)
    assert any(message.get("tool_calls") for message in messages if message["role"] == "assistant")
