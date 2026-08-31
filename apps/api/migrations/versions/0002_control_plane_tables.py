"""Add durable control-plane queue, worker registry, and Outbox.

Revision ID: 0002_control_plane_tables
Revises: 0001_legacy_schema
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_control_plane_tables"
down_revision: str | Sequence[str] | None = "0001_legacy_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("audit_events", "run_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("audit_events", sa.Column("resource_type", sa.String(), nullable=True))
    op.add_column("audit_events", sa.Column("resource_id", sa.UUID(), nullable=True))
    op.create_index("ix_audit_events_resource_type", "audit_events", ["resource_type"])
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"])

    op.create_table(
        "control_tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("capability", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner_id", sa.UUID(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_class", sa.String(), nullable=True),
        sa.Column("side_effect_certainty", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_control_tasks_idempotency_key"),
    )
    for name, columns in {
        "ix_control_tasks_kind": ["kind"], "ix_control_tasks_status": ["status"],
        "ix_control_tasks_capability": ["capability"], "ix_control_tasks_run_id": ["run_id"],
        "ix_control_tasks_available_at": ["available_at"],
        "ix_control_tasks_lease_owner_id": ["lease_owner_id"],
        "ix_control_tasks_lease_expires_at": ["lease_expires_at"],
        "ix_control_tasks_created_at": ["created_at"],
    }.items():
        op.create_index(name, "control_tasks", columns)

    op.create_table(
        "worker_registrations",
        sa.Column("id", sa.UUID(), nullable=False), sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False), sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("token_digest", sa.String(), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("token_digest", name="uq_worker_token_digest"),
    )
    for name, columns in {
        "ix_worker_registrations_name": ["name"], "ix_worker_registrations_token_digest": ["token_digest"],
        "ix_worker_registrations_status": ["status"],
        "ix_worker_registrations_last_heartbeat_at": ["last_heartbeat_at"],
        "ix_worker_registrations_created_at": ["created_at"],
    }.items():
        op.create_index(name, "worker_registrations", columns)

    op.create_table(
        "outbox_events",
        sa.Column("sequence", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False), sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False), sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("sequence"),
    )
    for name, columns in {
        "ix_outbox_events_event_type": ["event_type"], "ix_outbox_events_resource_type": ["resource_type"],
        "ix_outbox_events_resource_id": ["resource_id"], "ix_outbox_events_published_at": ["published_at"],
        "ix_outbox_events_created_at": ["created_at"],
    }.items():
        op.create_index(name, "outbox_events", columns)


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("worker_registrations")
    op.drop_table("control_tasks")
    op.drop_index("ix_audit_events_resource_id", table_name="audit_events")
    op.drop_index("ix_audit_events_resource_type", table_name="audit_events")
    op.drop_column("audit_events", "resource_id")
    op.drop_column("audit_events", "resource_type")
    op.alter_column("audit_events", "run_id", existing_type=sa.UUID(), nullable=False)
