import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlmodel import Session

from app.auth.models import Operator
from app.config import Settings, get_settings
from app.control.enums import SideEffectCertainty, TaskKind
from app.control.repositories import append_outbox_event, enqueue_task
from app.models import ActionStatus, ToolAction
from app.repositories import ActionRepository, AuditRepository, RunRepository
from app.services.audit import AuditService


class ApprovalError(RuntimeError):
    pass


class ApprovalNotFoundError(ApprovalError):
    pass


class ApprovalConflictError(ApprovalError):
    pass


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"


POLICY_VERSION = "local-demo-v1"
CONTROL_RUN_CAPABILITY = "control.run"


class ApprovalService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
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

    def decide(
        self,
        action_id: UUID,
        decision: ApprovalDecision,
        operator: Operator,
        note: str | None = None,
    ) -> ToolAction:
        return self._decide(action_id, decision, f"operator:{operator.id}", note)

    async def approve(self, action_id: UUID, actor: str, note: str | None = None) -> ToolAction:
        return self._decide(action_id, ApprovalDecision.APPROVED, actor, note)

    async def deny(self, action_id: UUID, actor: str, note: str | None = None) -> ToolAction:
        return self._decide(action_id, ApprovalDecision.DENIED, actor, note)

    def _decide(
        self,
        action_id: UUID,
        decision: ApprovalDecision,
        actor: str,
        note: str | None,
    ) -> ToolAction:
        action = self.action_repository.get(action_id)
        if action is None:
            raise ApprovalNotFoundError("tool action was not found")
        target = (
            ActionStatus.APPROVED
            if decision is ApprovalDecision.APPROVED
            else ActionStatus.DENIED
        )
        if not self.action_repository.transition(
            action_id, {ActionStatus.PENDING_APPROVAL}, target, commit=False
        ):
            raise ApprovalConflictError("tool action was already decided")
        action = self.action_repository.get(action_id)
        if action is None:
            raise ApprovalNotFoundError("tool action was not found after decision")
        self.audit.append(
            action.run_id,
            f"approval.{decision.value}",
            actor,
            {
                "note": note,
                "action_id": str(action.id),
                "arguments_sha256": hashlib.sha256(action.arguments_json.encode()).hexdigest(),
                "policy_version": POLICY_VERSION,
            },
            action.id,
            commit=False,
        )
        self._emit(
            action.run_id,
            "action.updated",
            {"action_id": str(action.id), "status": action.status.value},
        )

        if decision is ApprovalDecision.DENIED:
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
                actor,
                {"reason": action.reason},
                action.id,
                commit=False,
            )

        run = self.run_repository.get(action.run_id)
        if run is None:
            raise ApprovalNotFoundError("agent run was not found")
        if decision is ApprovalDecision.DENIED:
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
        task = enqueue_task(
            self.session,
            kind=TaskKind.AGENT_RUN,
            payload={"run_id": str(action.run_id)},
            idempotency_key=f"agent-run-resume:{action.run_id}:action:{action.id}",
            capability=CONTROL_RUN_CAPABILITY,
            run_id=action.run_id,
            side_effect_certainty=(
                SideEffectCertainty.POSSIBLE
                if decision is ApprovalDecision.APPROVED
                else SideEffectCertainty.READ_ONLY
            ),
        )
        self._emit(
            action.run_id,
            "task.queued",
            {"task_id": str(task.id), "action_id": str(action.id), "kind": task.kind.value},
        )
        self.session.commit()
        self.session.refresh(action)
        return action
