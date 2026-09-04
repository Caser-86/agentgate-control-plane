import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class RunStatus(str, Enum):  # noqa: UP042
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionStatus(str, Enum):  # noqa: UP042
    PROPOSED = "proposed"
    AUTO_APPROVED = "auto_approved"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    DENIED = "denied"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class RiskLevel(str, Enum):  # noqa: UP042
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PolicyDecision(str, Enum):  # noqa: UP042
    AUTO_APPROVE = "auto_approve"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


def utc_now() -> datetime:
    return datetime.now(UTC)


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_request: str
    status: RunStatus = Field(default=RunStatus.QUEUED, index=True)
    provider: str
    model: str
    step_count: int = 0
    conversation_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)
    error_message: str | None = None

    def messages(self) -> list[dict[str, Any]]:
        value = json.loads(self.conversation_json)
        return value if isinstance(value, list) else []


class ToolAction(SQLModel, table=True):
    __tablename__ = "tool_actions"
    __table_args__ = (
        Index(
            "uq_tool_actions_legacy_idempotency",
            "idempotency_key",
            unique=True,
            sqlite_where=text("proposer_client_id IS NULL"),
            postgresql_where=text("proposer_client_id IS NULL"),
        ),
        Index(
            "uq_tool_actions_client_idempotency",
            "proposer_client_id",
            "idempotency_key",
            unique=True,
            sqlite_where=text("proposer_client_id IS NOT NULL"),
            postgresql_where=text("proposer_client_id IS NOT NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID | None = Field(default=None, foreign_key="agent_runs.id", index=True)
    proposer_client_id: UUID | None = Field(
        default=None, foreign_key="client_tokens.id", index=True
    )
    tool_call_id: str
    tool_name: str
    target_type: str | None = None
    target_id: UUID | None = Field(default=None, index=True)
    action_version: str | None = None
    arguments_digest: str | None = None
    policy_version: str | None = None
    risk_level: RiskLevel
    policy_decision: PolicyDecision
    status: ActionStatus = Field(default=ActionStatus.PROPOSED, index=True)
    arguments_json: str = Field(default="{}")
    result_json: str | None = None
    reason: str = ""
    idempotency_key: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    decided_at: datetime | None = None
    executed_at: datetime | None = None
    approval_expires_at: datetime | None = Field(default=None, index=True)


class AuditEvent(SQLModel, table=True):
    __tablename__ = "audit_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID | None = Field(default=None, foreign_key="agent_runs.id", index=True)
    action_id: UUID | None = Field(default=None, index=True)
    resource_type: str | None = Field(default=None, index=True)
    resource_id: UUID | None = Field(default=None, index=True)
    event_type: str = Field(index=True)
    actor: str
    payload_json: str
    created_at: datetime = Field(default_factory=utc_now, index=True)


class ServiceState(SQLModel, table=True):
    __tablename__ = "service_states"

    service: str = Field(primary_key=True)
    health: str
    restart_count: int = 0
    last_restart_at: datetime | None = None
