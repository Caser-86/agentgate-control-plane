import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlmodel import Session, select

from app.control.enums import SideEffectCertainty, TaskKind, TaskStatus
from app.control.models import ControlTask
from app.control.repositories import append_outbox_event, enqueue_task_with_status
from app.files.models import ManagedWorkspace, QuarantineEntry
from app.files.security import InvalidRelativePath, normalize_relative_path, protected_match
from app.models import ActionStatus, PolicyDecision, RiskLevel, ToolAction, utc_now
from app.repositories import ActionRepository, AuditRepository
from app.schemas_actions import ActionStatusResponse, ExternalActionRequest
from app.services.audit import AuditService

SUPPORTED_FILE_ACTIONS = frozenset(
    {"file.inspect.v1", "file.quarantine.v1", "file.restore.v1"}
)
POLICY_VERSION = "file-policy.v1"


@dataclass(frozen=True)
class ActionCaller:
    client_id: UUID


@dataclass(frozen=True)
class PolicyEvaluation:
    decision: str
    risk_level: RiskLevel
    code: str
    reason: str
    requires_approval: bool


@dataclass(frozen=True)
class ReconciliationResult:
    action_id: UUID
    decision: str
    status: str
    reason: str


class ExternalActionError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code


class FileActionPolicy:
    def evaluate(
        self,
        action: str,
        workspace: ManagedWorkspace,
        arguments: dict[str, object],
        caller: ActionCaller,
    ) -> PolicyEvaluation:
        del caller
        if action not in SUPPORTED_FILE_ACTIONS:
            return PolicyEvaluation(
                "deny", RiskLevel.HIGH, "unsupported_action", "不支持此文件动作", False
            )
        if not workspace.enabled:
            return PolicyEvaluation(
                "deny", RiskLevel.MEDIUM, "workspace_disabled", "工作区已停用", False
            )
        if action != "file.restore.v1":
            relative_path = arguments.get("relative_path")
            if not isinstance(relative_path, str):
                return PolicyEvaluation(
                    "deny", RiskLevel.MEDIUM, "invalid_relative_path", "必须提供相对文件路径", False
                )
            try:
                normalized = normalize_relative_path(relative_path)
            except InvalidRelativePath:
                return PolicyEvaluation(
                    "deny",
                    RiskLevel.MEDIUM,
                    "invalid_relative_path",
                    "文件路径不安全，未执行任何变化",
                    False,
                )
            if action == "file.quarantine.v1" and protected_match(
                normalized, workspace.protected_patterns
            ):
                return PolicyEvaluation(
                    "deny",
                    RiskLevel.MEDIUM,
                    "protected_path",
                    "目标路径受保护，文件未执行任何变化",
                    False,
                )
        if action == "file.inspect.v1":
            return PolicyEvaluation(
                "allow_auto", RiskLevel.LOW, "read_only", "只读检查可以自动执行", False
            )
        return PolicyEvaluation(
            "require_approval",
            RiskLevel.MEDIUM,
            "human_approval_required",
            "该文件动作需要人工审批",
            True,
        )


def _digest(arguments: dict[str, object]) -> str:
    encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _status_for(decision: str) -> ActionStatus:
    return {
        "allow_auto": ActionStatus.AUTO_APPROVED,
        "require_approval": ActionStatus.PENDING_APPROVAL,
        "deny": ActionStatus.DENIED,
    }[decision]


class ExternalActionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(AuditRepository(session))
        self.actions = ActionRepository(session)

    def _request_arguments(
        self, request: ExternalActionRequest, workspace: ManagedWorkspace
    ) -> dict[str, object]:
        if request.action not in SUPPORTED_FILE_ACTIONS:
            raise ExternalActionError("unsupported_action", "不支持此文件动作", 403)
        arguments: dict[str, object] = {
            "workspace_id": str(workspace.id),
            "workspace_version": workspace.version,
        }
        if request.action != "file.restore.v1":
            assert request.relative_path is not None
            try:
                arguments["relative_path"] = normalize_relative_path(request.relative_path)
            except InvalidRelativePath as error:
                raise ExternalActionError(
                    "invalid_relative_path", "文件路径不安全，未执行任何变化"
                ) from error
        else:
            assert request.quarantine_entry_id is not None
            entry = self.session.get(QuarantineEntry, request.quarantine_entry_id)
            if entry is None or entry.workspace_id != workspace.id:
                raise ExternalActionError("quarantine_entry_not_found", "隔离记录不存在", 404)
            arguments["quarantine_entry_id"] = str(entry.id)
        if request.action == "file.quarantine.v1":
            arguments["reason"] = request.reason or "外部 Agent 请求隔离文件"
        return arguments

    def _response(self, action: ToolAction, task_id: UUID | None = None) -> ActionStatusResponse:
        arguments = json.loads(action.arguments_json)
        result = json.loads(action.result_json) if action.result_json else None
        return ActionStatusResponse(
            id=action.id,
            action=action.tool_name,
            workspace_id=UUID(str(arguments["workspace_id"])),
            relative_path=cast(str | None, arguments.get("relative_path")),
            quarantine_entry_id=(
                UUID(str(arguments["quarantine_entry_id"]))
                if arguments.get("quarantine_entry_id")
                else None
            ),
            decision={
                PolicyDecision.AUTO_APPROVE: "allow_auto",
                PolicyDecision.REQUIRE_APPROVAL: "require_approval",
                PolicyDecision.DENY: "deny",
            }[action.policy_decision],
            status=action.status.value,
            reason=action.reason,
            action_version=action.action_version or action.tool_name,
            task_id=task_id,
            approval_expires_at=action.approval_expires_at,
            created_at=action.created_at,
            result=result if isinstance(result, dict) else None,
        )

    def propose(
        self, client_id: UUID, request: ExternalActionRequest, idempotency_key: str
    ) -> ActionStatusResponse:
        if not idempotency_key or len(idempotency_key) > 160:
            raise ExternalActionError("invalid_idempotency_key", "幂等键格式不合法")
        existing = self.session.exec(
            select(ToolAction).where(
                cast(Any, ToolAction.proposer_client_id) == client_id,
                cast(Any, ToolAction.idempotency_key) == idempotency_key,
            )
        ).first()
        if existing is not None:
            try:
                workspace = self.session.get(ManagedWorkspace, request.workspace_id)
                arguments = self._request_arguments(request, workspace) if workspace else {}
                digest = _digest(arguments)
            except ExternalActionError:
                digest = ""
            if existing.arguments_digest != digest:
                raise ExternalActionError(
                    "idempotency_key_reused", "幂等键已用于不同动作，原动作未改变", 409
                )
            existing_task = self.session.exec(
                select(ControlTask).where(
                    cast(Any, ControlTask.proposer_client_id) == client_id,
                    cast(Any, ControlTask.idempotency_key)
                    == f"file-action:{existing.id}",
                )
            ).first()
            return self._response(existing, existing_task.id if existing_task else None)

        workspace = self.session.get(ManagedWorkspace, request.workspace_id)
        if workspace is None:
            raise ExternalActionError("workspace_not_found", "工作区不存在", 404)
        arguments = self._request_arguments(request, workspace)
        evaluation = FileActionPolicy().evaluate(
            request.action, workspace, arguments, ActionCaller(client_id)
        )
        now = datetime.now(UTC)
        action = ToolAction(
            run_id=None,
            proposer_client_id=client_id,
            tool_call_id=f"external:{uuid4()}",
            tool_name=request.action,
            target_type="managed_workspace",
            target_id=workspace.id,
            action_version=request.action,
            arguments_digest=_digest(arguments),
            policy_version=POLICY_VERSION,
            risk_level=evaluation.risk_level,
            policy_decision={
                "allow_auto": PolicyDecision.AUTO_APPROVE,
                "require_approval": PolicyDecision.REQUIRE_APPROVAL,
                "deny": PolicyDecision.DENY,
            }[evaluation.decision],
            status=_status_for(evaluation.decision),
            arguments_json=json.dumps(arguments, ensure_ascii=False, sort_keys=True),
            reason=evaluation.reason,
            idempotency_key=idempotency_key,
            decided_at=now,
            approval_expires_at=(
                now + timedelta(minutes=30) if evaluation.requires_approval else None
            ),
        )
        self.session.add(action)
        self.session.flush()

        task_id: UUID | None = None
        if evaluation.decision == "allow_auto":
            task_payload = {
                **arguments,
                "action_id": str(action.id),
                "arguments_digest": action.arguments_digest or "",
                "policy_version": action.policy_version or POLICY_VERSION,
            }
            task, _ = enqueue_task_with_status(
                self.session,
                kind=TaskKind.CONTROL,
                payload=task_payload,
                idempotency_key=f"file-action:{action.id}",
                capability=request.action,
                side_effect_certainty=SideEffectCertainty.READ_ONLY,
                proposer_client_id=client_id,
            )
            task_id = task.id
            self.audit.append(
                event_type="file.action.queued",
                actor=f"client:{client_id}",
                payload={"action": request.action, "workspace_id": str(workspace.id)},
                action_id=action.id,
                resource_type="tool_action",
                resource_id=action.id,
                commit=False,
            )
            append_outbox_event(
                self.session,
                event_type="task.queued",
                resource_type="control_task",
                resource_id=task.id,
                payload={"task_id": str(task.id), "capability": task.capability},
            )
        else:
            self.audit.append(
                event_type=(
                    "file.action.denied"
                    if evaluation.decision == "deny"
                    else "file.action.pending_approval"
                ),
                actor="policy",
                payload={
                    "action": request.action,
                    "workspace_id": str(workspace.id),
                    "relative_path": arguments.get("relative_path"),
                    "reason": evaluation.reason,
                },
                action_id=action.id,
                resource_type="tool_action",
                resource_id=action.id,
                commit=False,
            )
        self.session.commit()
        self.session.refresh(action)
        return self._response(action, task_id)

    def get_status(self, client_id: UUID, action_id: UUID) -> ActionStatusResponse:
        action = self.session.exec(
            select(ToolAction).where(
                cast(Any, ToolAction.id) == action_id,
                cast(Any, ToolAction.proposer_client_id) == client_id,
            )
        ).first()
        if action is None:
            raise ExternalActionError("not_found", "动作不存在", 404)
        task = self.session.exec(
            select(ControlTask).where(
                cast(Any, ControlTask.proposer_client_id) == client_id,
                cast(Any, ControlTask.idempotency_key) == f"file-action:{action.id}",
            )
        ).first()
        return self._response(action, task.id if task is not None else None)


def reconcile_file_action(session: Session, action_id: UUID) -> ReconciliationResult:
    action = session.get(ToolAction, action_id)
    if action is None or action.tool_name not in SUPPORTED_FILE_ACTIONS:
        raise ExternalActionError("not_found", "动作不存在", 404)
    if action.status in {
        ActionStatus.DENIED,
        ActionStatus.EXPIRED,
        ActionStatus.SUCCEEDED,
        ActionStatus.FAILED,
    }:
        return ReconciliationResult(
            action.id, "complete", action.status.value, "动作已经是终态"
        )

    candidates = session.exec(
        select(ControlTask).where(ControlTask.capability == action.tool_name)
    ).all()
    task = next(
        (
            candidate
            for candidate in candidates
            if candidate.payload.get("action_id") == str(action.id)
        ),
        None,
    )
    if task is not None and task.status == TaskStatus.QUEUED:
        return ReconciliationResult(action.id, "retry_safe", action.status.value, "任务尚未开始")
    if task is not None and task.status in {TaskStatus.LEASED, TaskStatus.RUNNING}:
        task.status = TaskStatus.MANUAL_REVIEW
        task.error_class = "file_action_manual_review_required"
        task.lease_owner_id = None
        task.lease_expires_at = None
        task.completed_at = utc_now()
        action.status = ActionStatus.FAILED
        action.result_json = json.dumps(
            {
                "status": "failed",
                "error_code": "manual_review_required",
                "error_message": "文件动作执行状态不确定，已停止自动重试",
            },
            ensure_ascii=False,
        )
        action.executed_at = task.completed_at
        session.add_all([task, action])
        AuditService(AuditRepository(session)).append(
            None,
            "file.action.manual_review_required",
            "system",
            {"action_id": str(action.id), "task_id": str(task.id)},
            action.id,
            resource_type="tool_action",
            resource_id=action.id,
            commit=False,
        )
        session.commit()
        return ReconciliationResult(
            action.id,
            "manual_review_required",
            action.status.value,
            "任务已开始但没有可信的完成回报",
        )
    if task is None:
        raise ExternalActionError("reconciliation_required", "动作缺少任务记录", 409)
    return ReconciliationResult(
        action.id, "complete", action.status.value, "任务已进入终态"
    )
