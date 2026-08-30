import json
from builtins import list as builtins_list
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlmodel import Session, select, update

from app.models import (
    ActionStatus,
    AgentRun,
    AuditEvent,
    RunStatus,
    ToolAction,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class RunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, user_request: str, provider: str, model: str) -> AgentRun:
        run = AgentRun(
            user_request=user_request,
            provider=provider,
            model=model,
            conversation_json="[]",
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get(self, run_id: UUID) -> AgentRun | None:
        return self.session.get(AgentRun, run_id)

    def list(self, limit: int = 50) -> list[AgentRun]:
        created_at = cast(Any, AgentRun.created_at)
        statement = select(AgentRun).order_by(created_at.desc()).limit(limit)
        return builtins_list(self.session.exec(statement).all())

    def set_status(
        self, run_id: UUID, expected: set[RunStatus], target: RunStatus
    ) -> bool:
        statement = (
            update(AgentRun)
            .where(
                cast(Any, AgentRun.id) == run_id,
                cast(Any, AgentRun.status).in_(expected),
            )
            .values(status=target, updated_at=utc_now())
        )
        result = self.session.exec(statement)
        self.session.commit()
        return result.rowcount == 1

    def save_checkpoint(
        self, run_id: UUID, messages: builtins_list[dict[str, object]], step_count: int
    ) -> None:
        statement = (
            update(AgentRun)
            .where(cast(Any, AgentRun.id) == run_id)
            .values(
                conversation_json=json.dumps(messages, ensure_ascii=False),
                step_count=step_count,
                updated_at=utc_now(),
            )
        )
        self.session.exec(statement)
        self.session.commit()


class ActionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, action: ToolAction) -> ToolAction:
        self.session.add(action)
        self.session.commit()
        self.session.refresh(action)
        return action

    def get(self, action_id: UUID) -> ToolAction | None:
        return self.session.get(ToolAction, action_id)

    def list_for_run(self, run_id: UUID) -> list[ToolAction]:
        statement = select(ToolAction).where(cast(Any, ToolAction.run_id) == run_id).order_by(
            cast(Any, ToolAction.created_at)
        )
        return builtins_list(self.session.exec(statement).all())

    def transition(
        self, action_id: UUID, expected: set[ActionStatus], target: ActionStatus
    ) -> bool:
        statement = (
            update(ToolAction)
            .where(
                cast(Any, ToolAction.id) == action_id,
                cast(Any, ToolAction.status).in_(expected),
            )
            .values(status=target, decided_at=utc_now())
        )
        result = self.session.exec(statement)
        self.session.commit()
        return result.rowcount == 1


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, event: AuditEvent) -> AuditEvent:
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def list(
        self,
        run_id: UUID | None = None,
        event_type: str | None = None,
        actor: str | None = None,
    ) -> list[AuditEvent]:
        statement = select(AuditEvent)
        if run_id is not None:
            statement = statement.where(cast(Any, AuditEvent.run_id) == run_id)
        if event_type is not None:
            statement = statement.where(cast(Any, AuditEvent.event_type) == event_type)
        if actor is not None:
            statement = statement.where(cast(Any, AuditEvent.actor) == actor)
        statement = statement.order_by(cast(Any, AuditEvent.created_at))
        return builtins_list(self.session.exec(statement).all())
