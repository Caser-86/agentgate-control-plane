from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateRunRequest(BaseModel):
    user_request: str = Field(min_length=5, max_length=2000)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)


class AuthStatusResponse(BaseModel):
    authenticated: bool
    setup_required: bool


class SetupRequest(BaseModel):
    bootstrap_token: str = Field(min_length=1, max_length=500)
    password: str = Field(min_length=6, max_length=512)


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)


class CsrfResponse(BaseModel):
    csrf_token: str


class CreateClientTokenRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: set[str] = Field(min_length=1)
    expires_in_seconds: int | None = Field(default=None, ge=60, le=31_536_000)
    rotate_token_id: UUID | None = None


class ClientTokenCreatedResponse(BaseModel):
    id: UUID
    name: str
    scopes: list[str]
    expires_at: datetime | None
    token: str


class EventProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=120)
    payload: dict[str, object] = Field(default_factory=dict)


class CheckProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_type: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=120)
    parameters: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=160)


class ActionProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=120)
    parameters: dict[str, object] = Field(default_factory=dict)


class ProposalResponse(BaseModel):
    id: UUID | None = None
    decision: str | None = None


class AgentRunResponse(BaseModel):
    id: UUID
    user_request: str
    status: str
    provider: str
    model: str
    step_count: int
    created_at: datetime
    updated_at: datetime
    error_message: str | None


class ToolActionResponse(BaseModel):
    id: UUID
    run_id: UUID
    tool_call_id: str
    tool_name: str
    risk_level: str
    policy_decision: str
    status: str
    arguments: dict[str, object]
    result: object | None
    reason: str
    created_at: datetime
    decided_at: datetime | None
    executed_at: datetime | None


class AuditEventResponse(BaseModel):
    id: UUID
    run_id: UUID | None
    action_id: UUID | None
    resource_type: str | None
    resource_id: UUID | None
    event_type: str
    actor: str
    payload: object
    created_at: datetime


class RunDetailResponse(AgentRunResponse):
    actions: list[ToolActionResponse]
    audit_events: list[AuditEventResponse]
    final_text: str | None


class TaskStatusResponse(BaseModel):
    id: UUID
    kind: str
    status: str
    attempts: int
    run_id: UUID | None
    available_at: datetime
    lease_expires_at: datetime | None
    result: object | None


class PolicyView(BaseModel):
    name: str
    description: str
    risk_level: str
    read_only: bool
    decision: str
    reason: str
