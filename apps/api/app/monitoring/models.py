from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel

from app.models import utc_now


class MonitorTarget(SQLModel, table=True):
    __tablename__ = "monitor_targets"
    __table_args__ = (Index("ix_monitor_targets_due", "enabled", "next_probe_at"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, max_length=128)
    kind: str = Field(index=True, max_length=32)
    endpoint: str = Field(max_length=2048)
    enabled: bool = Field(default=True, index=True)
    interval_seconds: int = Field(default=60)
    timeout_seconds: int = Field(default=5)
    failure_threshold: int = Field(default=3)
    recovery_threshold: int = Field(default=2)
    health: str = Field(default="unknown", index=True, max_length=16)
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_probe_status: str | None = Field(default=None, index=True, max_length=16)
    last_probe_detail: str | None = Field(default=None, max_length=512)
    last_latency_ms: int | None = None
    last_probe_at: datetime | None = None
    next_probe_at: datetime = Field(default_factory=utc_now, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class MonitorObservation(SQLModel, table=True):
    __tablename__ = "monitor_observations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    target_id: UUID = Field(foreign_key="monitor_targets.id", index=True)
    task_id: UUID | None = Field(default=None, foreign_key="control_tasks.id", index=True)
    status: str = Field(max_length=16, index=True)
    detail: str = Field(default="", max_length=512)
    latency_ms: int | None = None
    observed_at: datetime = Field(default_factory=utc_now, index=True)


class MonitorEvent(SQLModel, table=True):
    __tablename__ = "monitor_events"
    __table_args__ = (
        Index(
            "uq_monitor_events_active_target",
            "target_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    target_id: UUID = Field(foreign_key="monitor_targets.id", index=True)
    status: str = Field(default="active", index=True, max_length=16)
    reason: str = Field(default="", max_length=512)
    failure_count: int = 0
    opened_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)
    last_failure_at: datetime | None = None
    closed_at: datetime | None = None
