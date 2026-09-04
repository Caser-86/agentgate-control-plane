from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.files.security import normalize_relative_path

POLICY_VERSION = "file-policy.v1"


class FileTaskBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    workspace_id: UUID
    workspace_version: int = Field(gt=0)
    arguments_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_version: Literal["file-policy.v1"]


class FileInspectTask(FileTaskBase):
    relative_path: str = Field(min_length=1, max_length=4000)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return normalize_relative_path(value)


class FileQuarantineTask(FileTaskBase):
    relative_path: str = Field(min_length=1, max_length=4000)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return normalize_relative_path(value)


class FileRestoreTask(FileTaskBase):
    quarantine_entry_id: UUID


class WorkspaceContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    version: int
    root_path: str
    quarantine_root_path: str
    protected_patterns: list[str]
