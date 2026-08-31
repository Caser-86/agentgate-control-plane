import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlmodel import Session

from app.config import Settings, get_settings
from app.control.repositories import append_outbox_event
from app.llm.base import LLMProvider
from app.models import ActionStatus, RunStatus, ToolAction
from app.repositories import ActionRepository, AuditRepository, RunRepository
from app.services.agent_loop import AgentRunner
from app.services.audit import AuditService
from app.services.executor import ToolExecutor


class ApprovalError(RuntimeError):
    pass


class ApprovalNotFoundError(ApprovalError):
    pass


class ApprovalConflictError(ApprovalError):
    pass


class ApprovalService:
    def __init__(
        self,
        session: Session,
        *,
        runner: AgentRunner | None = None,
        executor: ToolExecutor | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.runner = runner
        self.executor = executor or ToolExecutor(session)
        self.action_repository = ActionRepository(session)
        self.run_repository = RunRepository(session)
        self.audit = AuditService(AuditRepository(session))

    def _emit(self, run_id: UUID, event_type: str, payload: dict[str, object]) -> None:
        append_outbox_event(
            self.session,
            event_type=event_type,
            resource_type="run",
            resource_id=run_id,
            payload=payload,
        )

    async def approve(self, action_id: UUID, actor: str, note: str | None = None) -> ToolAction:
        return await self._decide(action_id, "approved", actor, note)

    async def deny(self, action_id: UUID, actor: str, note: str | None = None) -> ToolAction:
        return await self._decide(action_id, "denied", actor, note)

    async def _decide(
        self,
        action_id: UUID,
        decision: Literal["approved", "denied"],
        actor: str,
        note: str | None,
    ) -> ToolAction:
        action = self.action_repository.get(action_id)
        if action is None:
            raise ApprovalNotFoundError("tool action was not found")
        target = ActionStatus.APPROVED if decision == "approved" else ActionStatus.DENIED
        if not self.action_repository.transition(
            action_id, {ActionStatus.PENDING_APPROVAL}, target, commit=False
        ):
            raise ApprovalConflictError("tool action was already decided")
        action = self.action_repository.get(action_id)
        if action is None:
            raise ApprovalNotFoundError("tool action was not found after decision")
        self.audit.append(
            action.run_id,
            f"approval.{decision}",
            "user",
            {"actor": actor, "note": note, "action_id": str(action.id)},
            action.id,
            commit=False,
        )
        self._emit(
            action.run_id,
            "action.updated",
            {"action_id": str(action.id), "status": action.status.value},
        )

        if decision == "approved":
            self.session.commit()
            action = await self.executor.execute(action.id)
        else:
            action.result_json = json.dumps(
                {"denied": True, "reason": action.reason}, ensure_ascii=False
            )
            action.executed_at = datetime.now(UTC)
            self.session.add(action)
            self._emit(
                action.run_id,
                "action.updated",
                {"action_id": str(action.id), "status": action.status.value},
            )
            self.audit.append(
                action.run_id,
                "tool.denied",
                "user",
                {"reason": action.reason, "actor": actor},
                action.id,
                commit=False,
            )

        run = self.run_repository.get(action.run_id)
        if run is None:
            raise ApprovalNotFoundError("agent run was not found")
        messages = run.messages()
        messages.append(
            {
                "role": "tool",
                "tool_call_id": action.tool_call_id,
                "name": action.tool_name,
                "content": action.result_json or "{}",
            }
        )
        self.run_repository.save_checkpoint(
            action.run_id, messages, run.step_count, commit=False
        )
        self.run_repository.set_status(
            action.run_id, {RunStatus.WAITING_APPROVAL}, RunStatus.RUNNING, commit=False
        )
        self._emit(
            action.run_id,
            "run.updated",
            {"status": RunStatus.RUNNING.value, "action_id": str(action.id)},
        )
        self.session.commit()
        self.session.refresh(action)
        runner = self.runner or AgentRunner(
            self.session,
            provider=self._provider(),
            provider_name=self.settings.llm_provider,
            model=self.settings.llm_model,
            max_steps=self.settings.max_steps,
            run_timeout_seconds=self.settings.run_timeout_seconds,
        )
        await runner.resume_run(action.run_id)
        return self.action_repository.get(action.id) or action

    def _provider(self) -> LLMProvider:
        from app.services.runs import build_provider

        return build_provider(self.settings)
