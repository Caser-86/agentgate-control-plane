import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlmodel import Session

from app.auth.models import Operator
from app.config import Settings, get_settings
from app.control.enums import SideEffectCertainty, TaskKind
from app.control.repositories import append_outbox_event, enqueue_task, enqueue_task_with_status
from app.files.models import ManagedWorkspace
from app.models import ActionStatus, ToolAction
from app.repositories import ActionRepository, AuditRepository, RunRepository
from app.services.audit import AuditService
from app.services.file_actions import SUPPORTED_FILE_ACTIONS


class ApprovalError(RuntimeError):
    pass


class ApprovalNotFoundError(ApprovalError):
    pass


class ApprovalConflictError(ApprovalError):
    pass


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"


POLICY_VERSION = "local-policy-v1"
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
        if action.run_id is None and action.tool_name in SUPPORTED_FILE_ACTIONS:
            return self._decide_file_action(action, decision, actor, note)
        run_id = action.run_id
        if run_id is None:
            raise ApprovalConflictError("动作缺少关联运行")
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
            run_id,
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
        if decision is ApprovalDecision.DENIED:
            action.result_json = json.dumps(
                {"denied": True, "reason": action.reason}, ensure_ascii=False
            )
            action.executed_at = datetime.now(UTC)
            self.session.add(action)
            self.audit.append(
                run_id,
                "tool.denied",
                actor,
                {"reason": action.reason},
                action.id,
                commit=False,
            )

        run = self.run_repository.get(run_id)
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
                run_id, messages, run.step_count, commit=False
            )
            self._emit(
                run_id,
                "action.updated",
                {"action_id": str(action.id), "status": action.status.value},
            )
        else:
            self._emit(
                run_id,
                "action.updated",
                {"action_id": str(action.id), "status": action.status.value},
            )
        task = enqueue_task(
            self.session,
            kind=TaskKind.AGENT_RUN,
            payload={"run_id": str(run_id)},
            idempotency_key=f"agent-run-resume:{run_id}:action:{action.id}",
            capability=CONTROL_RUN_CAPABILITY,
            run_id=run_id,
            side_effect_certainty=(
                SideEffectCertainty.POSSIBLE
                if decision is ApprovalDecision.APPROVED
                else SideEffectCertainty.READ_ONLY
            ),
        )
        self._emit(
            run_id,
            "task.queued",
            {"task_id": str(task.id), "action_id": str(action.id), "kind": task.kind.value},
        )
        self.session.commit()
        self.session.refresh(action)
        return action

    def _decide_file_action(
        self,
        action: ToolAction,
        decision: ApprovalDecision,
        actor: str,
        note: str | None,
    ) -> ToolAction:
        try:
            arguments = json.loads(action.arguments_json)
            workspace_id = UUID(str(arguments["workspace_id"]))
            workspace_version = arguments["workspace_version"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ApprovalConflictError("文件动作参数已损坏") from error
        if not isinstance(arguments, dict) or not isinstance(workspace_version, int):
            raise ApprovalConflictError("文件动作参数已损坏")

        workspace = self.session.get(ManagedWorkspace, workspace_id)
        if workspace is None:
            raise ApprovalNotFoundError("工作区不存在")
        if (
            decision is ApprovalDecision.APPROVED
            and workspace.version != workspace_version
        ):
            raise ApprovalConflictError("工作区版本已变化，审批未执行")
        if decision is ApprovalDecision.APPROVED and action.approval_expires_at is not None:
            expiry = action.approval_expires_at
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if expiry <= datetime.now(UTC):
                self.action_repository.transition(
                    action.id,
                    {ActionStatus.PENDING_APPROVAL},
                    ActionStatus.EXPIRED,
                    commit=False,
                )
                action = self.action_repository.get(action.id) or action
                action.executed_at = datetime.now(UTC)
                self.session.add(action)
                self.session.commit()
                raise ApprovalConflictError("审批已过期，文件未执行")

        target = (
            ActionStatus.APPROVED
            if decision is ApprovalDecision.APPROVED
            else ActionStatus.DENIED
        )
        if not self.action_repository.transition(
            action.id, {ActionStatus.PENDING_APPROVAL}, target, commit=False
        ):
            raise ApprovalConflictError("文件动作已经被处理")
        action = self.action_repository.get(action.id) or action
        self.audit.append(
            None,
            f"file.action.{decision.value}",
            actor,
            {
                "note": note,
                "action_id": str(action.id),
                "workspace_id": str(workspace.id),
                "arguments_sha256": hashlib.sha256(action.arguments_json.encode()).hexdigest(),
            },
            action.id,
            resource_type="tool_action",
            resource_id=action.id,
            commit=False,
        )
        if decision is ApprovalDecision.DENIED:
            action.result_json = json.dumps(
                {"status": "denied", "reason": "人工拒绝，文件未执行任何变化"},
                ensure_ascii=False,
            )
            action.executed_at = datetime.now(UTC)
            self.session.add(action)
            self.session.commit()
            self.session.refresh(action)
            return action

        task_payload = {
            **arguments,
            "action_id": str(action.id),
            "arguments_digest": action.arguments_digest or "",
            "policy_version": action.policy_version or "file-policy.v1",
        }
        task, created = enqueue_task_with_status(
            self.session,
            kind=TaskKind.CONTROL,
            payload=task_payload,
            idempotency_key=f"file-action:{action.id}",
            capability=action.tool_name,
            proposer_client_id=action.proposer_client_id,
            side_effect_certainty=(
                SideEffectCertainty.READ_ONLY
                if action.tool_name == "file.inspect.v1"
                else SideEffectCertainty.POSSIBLE
            ),
        )
        if created:
            append_outbox_event(
                self.session,
                event_type="task.queued",
                resource_type="control_task",
                resource_id=task.id,
                payload={"task_id": str(task.id), "action_id": str(action.id)},
            )
        self.session.commit()
        self.session.refresh(action)
        return action
