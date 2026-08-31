import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlmodel import Session

from app.control.repositories import append_outbox_event
from app.llm.base import LLMProvider, ToolCall
from app.models import (
    ActionStatus,
    AgentRun,
    PolicyDecision,
    RunStatus,
    ToolAction,
)
from app.policy import PolicyEngine
from app.repositories import ActionRepository, AuditRepository, RunRepository
from app.services.audit import AuditService
from app.services.executor import ToolExecutor
from app.tools.registry import ToolRegistry, UnknownToolError


class AgentRunner:
    def __init__(
        self,
        session: Session,
        *,
        provider: LLMProvider,
        provider_name: str = "mock",
        model: str = "mock-operations-agent",
        registry: ToolRegistry | None = None,
        max_steps: int = 8,
        run_timeout_seconds: float = 120,
    ) -> None:
        self.session = session
        self.provider = provider
        self.provider_name = provider_name
        self.model = model
        self.registry = registry or ToolRegistry()
        self.policy = PolicyEngine()
        self.run_repository = RunRepository(session)
        self.action_repository = ActionRepository(session)
        self.audit = AuditService(AuditRepository(session))
        self.executor = ToolExecutor(
            session,
            registry=self.registry,
            audit=AuditRepository(session),
        )
        self.max_steps = max_steps
        self.run_timeout_seconds = run_timeout_seconds

    def _emit(self, run_id: UUID, event_type: str, payload: dict[str, object]) -> None:
        append_outbox_event(
            self.session,
            event_type=event_type,
            resource_type="run",
            resource_id=run_id,
            payload=payload,
        )

    def create_run(self, user_request: str) -> AgentRun:
        run = self.run_repository.create(user_request, self.provider_name, self.model, commit=False)
        messages: list[dict[str, object]] = [{"role": "user", "content": user_request}]
        self.run_repository.save_checkpoint(run.id, messages, 0, commit=False)
        self.audit.append(
            run.id, "run.created", "user", {"user_request": user_request}, commit=False
        )
        self.session.commit()
        self.session.refresh(run)
        return self.run_repository.get(run.id) or run

    async def start_run(self, user_request: str) -> UUID:
        run = self.create_run(user_request)
        await self.resume_run(run.id)
        return run.id

    async def resume_run(self, run_id: UUID) -> None:
        try:
            async with asyncio.timeout(self.run_timeout_seconds):
                await self._run(run_id)
        except TimeoutError:
            self._fail_run(run_id, "run exceeded the configured timeout")
        except Exception:
            self._fail_run(run_id, "run failed safely")

    async def _run(self, run_id: UUID) -> None:
        run = self.run_repository.get(run_id)
        if run is None:
            return
        if run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
            return
        if run.status in {RunStatus.QUEUED, RunStatus.WAITING_APPROVAL}:
            changed = self.run_repository.set_status(
                run_id,
                {RunStatus.QUEUED, RunStatus.WAITING_APPROVAL},
                RunStatus.RUNNING,
                commit=False,
            )
            if changed:
                self._emit(run_id, "run.updated", {"status": RunStatus.RUNNING.value})
                self.session.commit()
        messages = run.messages()

        if await self._resume_approved_action(run_id, messages):
            run = self.run_repository.get(run_id)
            if run is None:
                return
            messages = run.messages()

        while True:
            run = self.run_repository.get(run_id)
            if run is None:
                return
            if run.step_count >= self.max_steps:
                self._fail_run(run_id, "maximum agent steps exceeded")
                return
            step_count = run.step_count + 1
            self.run_repository.save_checkpoint(run_id, messages, step_count)
            turn = await self.provider.complete(messages, self.registry.schemas())
            messages.append(turn.assistant_message)
            self.run_repository.save_checkpoint(run_id, messages, step_count)

            if not turn.tool_calls:
                self.run_repository.set_status(
                    run_id, {RunStatus.RUNNING}, RunStatus.COMPLETED, commit=False
                )
                self._emit(run_id, "run.updated", {"status": RunStatus.COMPLETED.value})
                self.audit.append(
                    run_id,
                    "run.completed",
                    "agent",
                    {"final_text": turn.text or ""},
                    commit=False,
                )
                self.session.commit()
                return

            for call in turn.tool_calls:
                result, pending = await self._handle_tool_call(run_id, call, messages, step_count)
                if result is not None:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": result,
                        }
                    )
                    self.run_repository.save_checkpoint(run_id, messages, step_count)
                if pending:
                    return

    async def _resume_approved_action(
        self, run_id: UUID, messages: list[dict[str, object]]
    ) -> bool:
        """Execute an already-approved action exactly once from the worker path."""
        approved = next(
            (
                action
                for action in self.action_repository.list_for_run(run_id)
                if action.status is ActionStatus.APPROVED
            ),
            None,
        )
        if approved is None:
            return False
        executed = await self.executor.execute(approved.id)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": executed.tool_call_id,
                "name": executed.tool_name,
                "content": executed.result_json or '{"error":"tool returned no result"}',
            }
        )
        run = self.run_repository.get(run_id)
        if run is not None:
            self.run_repository.save_checkpoint(run_id, messages, run.step_count, commit=False)
            self._emit(
                run_id,
                "action.updated",
                {"action_id": str(executed.id), "status": executed.status.value},
            )
            self.session.commit()
        return True

    async def _handle_tool_call(
        self,
        run_id: UUID,
        call: ToolCall,
        messages: list[dict[str, object]],
        step_count: int,
    ) -> tuple[str | None, bool]:
        del messages
        try:
            registered = self.registry.get(call.name)
        except UnknownToolError:
            action = self._create_action(
                run_id,
                call.id,
                call.name,
                call.arguments,
                risk_level="high",
                decision=PolicyDecision.DENY,
                status=ActionStatus.DENIED,
                reason="Unknown tools are denied by the allowlist.",
            )
            result = {"error": "unknown tool denied", "tool": call.name}
            self._save_result(action, result)
            self._emit(
                run_id,
                "action.updated",
                {"action_id": str(action.id), "status": action.status.value},
            )
            self.audit.append(run_id, "tool.denied", "policy", result, action.id, commit=False)
            self.session.commit()
            return json.dumps(result), False

        try:
            self.registry.validate(call.name, call.arguments)
        except ValidationError:
            action = self._create_action(
                run_id,
                call.id,
                call.name,
                call.arguments,
                risk_level=registered.spec.risk_level.value,
                decision=PolicyDecision.DENY,
                status=ActionStatus.DENIED,
                reason="Tool arguments failed schema validation.",
            )
            result = {"error": "tool arguments failed schema validation"}
            self._save_result(action, result)
            self._emit(
                run_id,
                "action.updated",
                {"action_id": str(action.id), "status": action.status.value},
            )
            self.audit.append(run_id, "tool.denied", "policy", result, action.id, commit=False)
            self.session.commit()
            return json.dumps(result), False

        policy_result = self.policy.evaluate(registered.spec, call.arguments)
        action_status = {
            PolicyDecision.AUTO_APPROVE: ActionStatus.AUTO_APPROVED,
            PolicyDecision.REQUIRE_APPROVAL: ActionStatus.PENDING_APPROVAL,
            PolicyDecision.DENY: ActionStatus.DENIED,
        }[policy_result.decision]
        action = self._create_action(
            run_id,
            call.id,
            call.name,
            call.arguments,
            risk_level=policy_result.risk_level.value,
            decision=policy_result.decision,
            status=action_status,
            reason=policy_result.reason,
        )
        if policy_result.decision is PolicyDecision.DENY:
            result = {"error": "action denied", "reason": policy_result.reason}
            self._save_result(action, result)
            self._emit(
                run_id,
                "action.updated",
                {"action_id": str(action.id), "status": action.status.value},
            )
            self.audit.append(run_id, "tool.denied", "policy", result, action.id, commit=False)
            self.session.commit()
            return json.dumps(result), False
        self._emit(
            run_id,
            "action.updated",
            {"action_id": str(action.id), "status": action.status.value},
        )
        self.audit.append(
            run_id,
            "policy.decision",
            "policy",
            {
                "tool_name": call.name,
                "decision": policy_result.decision.value,
                "risk_level": policy_result.risk_level.value,
                "reason": policy_result.reason,
            },
            action.id,
        )

        if policy_result.decision is PolicyDecision.REQUIRE_APPROVAL:
            self.run_repository.set_status(
                run_id, {RunStatus.RUNNING}, RunStatus.WAITING_APPROVAL, commit=False
            )
            self._emit(
                run_id,
                "run.updated",
                {"status": RunStatus.WAITING_APPROVAL.value, "action_id": str(action.id)},
            )
            self.audit.append(
                run_id,
                "run.waiting_approval",
                "system",
                {"action_id": str(action.id), "step_count": step_count},
                action.id,
                commit=False,
            )
            self.session.commit()
            return None, True
        self.session.commit()
        executed = await self.executor.execute(action.id)
        self._emit(
            run_id,
            "action.updated",
            {"action_id": str(action.id), "status": executed.status.value},
        )
        self.session.commit()
        return executed.result_json or json.dumps({"error": "tool returned no result"}), False

    def _create_action(
        self,
        run_id: UUID,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, object],
        *,
        risk_level: str,
        decision: PolicyDecision,
        status: ActionStatus,
        reason: str,
    ) -> ToolAction:
        from app.models import RiskLevel

        action = ToolAction(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            risk_level=RiskLevel(risk_level),
            policy_decision=decision,
            status=status,
            arguments_json=json.dumps(arguments, ensure_ascii=False),
            reason=reason,
            idempotency_key=f"{run_id}:{tool_call_id}",
            decided_at=datetime.now(UTC),
        )
        return self.action_repository.create(action, commit=False)

    def _save_result(self, action: ToolAction, result: Mapping[str, object]) -> None:
        action.result_json = json.dumps(result, ensure_ascii=False)
        action.executed_at = datetime.now(UTC)
        self.session.add(action)
        self.session.flush()

    def _fail_run(self, run_id: UUID, message: str) -> None:
        run = self.run_repository.get(run_id)
        if run is None:
            return
        run.status = RunStatus.FAILED
        run.error_message = message
        run.updated_at = datetime.now(UTC)
        self.session.add(run)
        self.audit.append(run_id, "run.failed", "system", {"error": message}, commit=False)
        self._emit(run_id, "run.updated", {"status": RunStatus.FAILED.value})
        self.session.commit()
