from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExternalActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=64)
    workspace_id: UUID
    relative_path: str | None = Field(default=None, max_length=4000)
    quarantine_entry_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_action_arguments(self) -> "ExternalActionRequest":
        if self.action in {"file.inspect.v1", "file.quarantine.v1"} and not self.relative_path:
            raise ValueError("relative_path is required for this file action")
        if self.action == "file.restore.v1" and self.quarantine_entry_id is None:
            raise ValueError("quarantine_entry_id is required for restore")
        return self


class ActionStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    workspace_id: UUID
    relative_path: str | None
    quarantine_entry_id: UUID | None
    decision: str
    status: str
    reason: str
    action_version: str
    task_id: UUID | None
    approval_expires_at: datetime | None
    created_at: datetime
    result: object | None = None
