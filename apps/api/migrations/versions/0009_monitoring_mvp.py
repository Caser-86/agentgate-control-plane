"""Add persistent local monitoring targets, observations, and events."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0009_monitoring_mvp"
down_revision: str | Sequence[str] | None = "0008_operator_installation_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monitor_targets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=2048), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("failure_threshold", sa.Integer(), nullable=False),
        sa.Column("recovery_threshold", sa.Integer(), nullable=False),
        sa.Column("health", sa.String(length=16), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("consecutive_successes", sa.Integer(), nullable=False),
        sa.Column("last_probe_status", sa.String(length=16), nullable=True),
        sa.Column("last_probe_detail", sa.String(length=512), nullable=True),
        sa.Column("last_latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_probe_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in {
        "ix_monitor_targets_name": ["name"],
        "ix_monitor_targets_kind": ["kind"],
        "ix_monitor_targets_enabled": ["enabled"],
        "ix_monitor_targets_health": ["health"],
        "ix_monitor_targets_last_probe_status": ["last_probe_status"],
        "ix_monitor_targets_next_probe_at": ["next_probe_at"],
        "ix_monitor_targets_created_at": ["created_at"],
        "ix_monitor_targets_due": ["enabled", "next_probe_at"],
    }.items():
        op.create_index(name, "monitor_targets", columns)

    op.create_table(
        "monitor_observations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.String(length=512), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["target_id"], ["monitor_targets.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["control_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in {
        "ix_monitor_observations_target_id": ["target_id"],
        "ix_monitor_observations_task_id": ["task_id"],
        "ix_monitor_observations_status": ["status"],
        "ix_monitor_observations_observed_at": ["observed_at"],
    }.items():
        op.create_index(name, "monitor_observations", columns)

    op.create_table(
        "monitor_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["target_id"], ["monitor_targets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in {
        "ix_monitor_events_target_id": ["target_id"],
        "ix_monitor_events_status": ["status"],
        "ix_monitor_events_opened_at": ["opened_at"],
    }.items():
        op.create_index(name, "monitor_events", columns)
    op.create_index(
        "uq_monitor_events_active_target",
        "monitor_events",
        ["target_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_monitor_events_active_target", table_name="monitor_events")
    op.drop_table("monitor_events")
    op.drop_table("monitor_observations")
    op.drop_index("ix_monitor_targets_due", table_name="monitor_targets")
    op.drop_table("monitor_targets")
