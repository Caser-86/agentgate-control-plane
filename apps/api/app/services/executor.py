import asyncio
import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from pydantic import ValidationError
from sqlmodel import Session

from app.control.repositories import append_outbox_event
from app.models import ActionStatus, ToolAction
from app.repositories import ActionRepository, AuditRepository
from app.services.audit import AuditService
from app.tools.registry import ToolRegistry, UnknownToolError


class ExecutionError(RuntimeError):
    pass


class ActionNotFoundError(ExecutionError):
    pass


class ExecutionNotAllowedError(ExecutionError):
    pass


class ToolExecutor:
    def __init__(
        self,
        session: Session,
        *,
        registry: ToolRegistry | None = None,
        audit: AuditRepository | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        self.session = session
        self.registry = registry or ToolRegistry()
        self.action_repository = ActionRepository(session)
        self.audit = AuditService(audit or AuditRepository(session))
        self.timeout_seconds = timeout_seconds

    def _emit(self, action: ToolAction) -> None:
        append_outbox_event(
            self.session,
            event_type="action.updated",
            resource_type="run",
            resource_id=action.run_id,
            payload={"action_id": str(action.id), "status": action.status.value},
        )

    async def execute(self, action_id: UUID) -> ToolAction:
        action = self.action_repository.get(action_id)
        if action is None:
            raise ActionNotFoundError("tool action was not found")
        if action.status is ActionStatus.SUCCEEDED:
            return action
        if action.status not in {ActionStatus.AUTO_APPROVED, ActionStatus.APPROVED}:
            raise ExecutionNotAllowedError("tool action is not approved for execution")

        claimed = self.action_repository.transition(
            action_id,
            {ActionStatus.AUTO_APPROVED, ActionStatus.APPROVED},
            ActionStatus.RUNNING,
            commit=False,
        )
        if not claimed:
            latest = self.action_repository.get(action_id)
            if latest is not None and latest.status is ActionStatus.SUCCEEDED:
                return latest
            raise ExecutionNotAllowedError("tool action is already being executed")

        action = self.action_repository.get(action_id)
        if action is None:
            raise ActionNotFoundError("tool action disappeared during execution")
        self._emit(action)
        await self._audit_started(action, commit=False)
        self.session.commit()

        try:
            registered = self.registry.get(action.tool_name)
            decoded = json.loads(action.arguments_json)
            if not isinstance(decoded, dict):
                raise ValidationError.from_exception_data(
                    "tool_arguments",
                    [{"type": "dict_type", "loc": (), "input": decoded}],
                )
            arguments = self.registry.validate(action.tool_name, cast(dict[str, object], decoded))
            if registered.handler is None:
                raise ExecutionError("tool has no executable handler")
            async with asyncio.timeout(self.timeout_seconds):
                result = await registered.handler(arguments, self.session)
        except TimeoutError:
            return await self._fail(action_id, "tool execution timed out")
        except (ValidationError, UnknownToolError, ExecutionError, ValueError):
            return await self._deny(action_id, "tool execution was denied safely")
        except Exception:
            return await self._fail(action_id, "tool execution failed safely")

        action = self.action_repository.get(action_id)
        if action is None:
            raise ActionNotFoundError("tool action disappeared after execution")
        action.status = ActionStatus.SUCCEEDED
        action.result_json = json.dumps(result, ensure_ascii=False, default=str)
        action.executed_at = datetime.now(UTC)
        self.session.add(action)
        self._emit(action)
        self.audit.append(
            action.run_id,
            "tool.succeeded",
            "tool",
            {"tool_name": action.tool_name, "result": result},
            action.id,
            commit=False,
        )
        self.session.commit()
        self.session.refresh(action)
        return action

    async def _audit_started(self, action: ToolAction, *, commit: bool = True) -> None:
        self.audit.append(
            action.run_id,
            "tool.started",
            "tool",
            {"tool_name": action.tool_name},
            action.id,
            commit=commit,
        )

    async def _fail(self, action_id: UUID, message: str) -> ToolAction:
        action = self.action_repository.get(action_id)
        if action is None:
            raise ActionNotFoundError("tool action disappeared while failing")
        action.status = ActionStatus.FAILED
        action.result_json = json.dumps({"error": message}, ensure_ascii=False)
        action.executed_at = datetime.now(UTC)
        self.session.add(action)
        self._emit(action)
        self.audit.append(
            action.run_id,
            "tool.failed",
            "tool",
            {"tool_name": action.tool_name, "error": message},
            action.id,
            commit=False,
        )
        self.session.commit()
        self.session.refresh(action)
        return action

    async def _deny(self, action_id: UUID, message: str) -> ToolAction:
        action = self.action_repository.get(action_id)
        if action is None:
            raise ActionNotFoundError("tool action disappeared while denying execution")
        action.status = ActionStatus.DENIED
        action.result_json = json.dumps({"denied": True, "reason": message}, ensure_ascii=False)
        action.executed_at = datetime.now(UTC)
        self.session.add(action)
        self._emit(action)
        self.audit.append(
            action.run_id,
            "tool.denied",
            "tool",
            {"tool_name": action.tool_name, "reason": message},
            action.id,
            commit=False,
        )
        self.session.commit()
        self.session.refresh(action)
        return action
