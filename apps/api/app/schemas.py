from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    user_request: str = Field(min_length=5, max_length=2000)


class ApprovalRequest(BaseModel):
    actor: str = Field(default="local-user", min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)


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
    run_id: UUID
    action_id: UUID | None
    event_type: str
    actor: str
    payload: object
    created_at: datetime


class RunDetailResponse(AgentRunResponse):
    actions: list[ToolActionResponse]
    audit_events: list[AuditEventResponse]
    final_text: str | None


class PolicyView(BaseModel):
    name: str
    description: str
    risk_level: str
    read_only: bool
    decision: str
    reason: str
