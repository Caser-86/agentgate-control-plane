from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    root_path: str = Field(min_length=1, max_length=2048)
    protected_patterns: list[str] | None = None


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    root_path: str | None = Field(default=None, min_length=1, max_length=2048)
    protected_patterns: list[str] | None = None
    enabled: bool | None = None


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    root_path: str
    quarantine_root_path: str
    protected_patterns: list[str]
    enabled: bool
    version: int
    created_at: datetime
    updated_at: datetime


class QuarantineEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    action_id: UUID
    original_relative_path: str
    quarantine_relative_path: str
    content_sha256: str
    size_bytes: int
    status: str
    created_at: datetime
    restored_at: datetime | None


class QuarantineEntryListResponse(BaseModel):
    items: list[QuarantineEntryResponse]
