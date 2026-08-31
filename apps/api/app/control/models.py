from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, Column, Integer
from sqlmodel import Field, SQLModel

from app.control.enums import SideEffectCertainty, TaskKind, TaskStatus, WorkerStatus
from app.models import utc_now


class ControlTask(SQLModel, table=True):
    __tablename__ = "control_tasks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    kind: TaskKind = Field(index=True)
    status: TaskStatus = Field(default=TaskStatus.QUEUED, index=True)
    payload: dict[str, object] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    capability: str = Field(index=True)
    idempotency_key: str = Field(index=True)
    proposer_client_id: UUID | None = Field(
        default=None, foreign_key="client_tokens.id", index=True
    )
    run_id: UUID | None = Field(default=None, foreign_key="agent_runs.id", index=True)
    attempts: int = 0
    lease_version: int = 0
    available_at: datetime = Field(default_factory=utc_now, index=True)
    lease_owner_id: UUID | None = Field(default=None, index=True)
    lease_expires_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, object] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    error_class: str | None = None
    side_effect_certainty: SideEffectCertainty = Field(default=SideEffectCertainty.READ_ONLY)


class WorkerRegistration(SQLModel, table=True):
    __tablename__ = "worker_registrations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    version: str
    protocol_version: str = Field(default="1.0")
    capabilities: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    token_digest: str = Field(unique=True, index=True)
    status: WorkerStatus = Field(default=WorkerStatus.ACTIVE, index=True)
    last_heartbeat_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkerExecutionGrant(SQLModel, table=True):
    __tablename__ = "worker_execution_grants"

    task_id: UUID = Field(primary_key=True, foreign_key="control_tasks.id")
    worker_id: UUID = Field(foreign_key="worker_registrations.id", index=True)
    lease_version: int = Field(index=True)
    request_digest: str = Field(index=True)
    lease_expires_at: datetime = Field(index=True)
    started_at: datetime = Field(default_factory=utc_now, index=True)
    completed_at: datetime | None = Field(default=None, index=True)


class OutboxEvent(SQLModel, table=True):
    __tablename__ = "outbox_events"

    sequence: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
        ),
    )
    event_type: str = Field(index=True)
    resource_type: str = Field(index=True)
    resource_id: UUID = Field(index=True)
    payload: dict[str, object] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    published_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
