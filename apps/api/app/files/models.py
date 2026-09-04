from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models import utc_now


class ManagedWorkspace(SQLModel, table=True):
    __tablename__ = "managed_workspaces"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=128, index=True)
    root_path: str = Field(max_length=2048)
    canonical_root_path: str = Field(max_length=2048)
    quarantine_root_path: str = Field(max_length=2048)
    protected_patterns: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    enabled: bool = Field(default=True, index=True)
    version: int = Field(default=1, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class QuarantineEntry(SQLModel, table=True):
    __tablename__ = "quarantine_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="managed_workspaces.id", index=True)
    action_id: UUID = Field(foreign_key="tool_actions.id", index=True)
    original_relative_path: str = Field(max_length=4000)
    quarantine_relative_path: str = Field(max_length=4000)
    content_sha256: str = Field(max_length=64)
    size_bytes: int
    status: str = Field(default="quarantined", index=True, max_length=16)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    restored_at: datetime | None = None
