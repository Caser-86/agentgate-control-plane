"""Create the legacy AgentGate schema.

Revision ID: 0001_legacy_schema
Revises:
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_legacy_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    run_status = sa.Enum(
        "QUEUED", "RUNNING", "WAITING_APPROVAL", "COMPLETED", "FAILED", "CANCELLED", name="runstatus"
    )
    action_status = sa.Enum(
        "PROPOSED", "AUTO_APPROVED", "PENDING_APPROVAL", "APPROVED", "DENIED", "RUNNING",
        "SUCCEEDED", "FAILED", "EXPIRED", name="actionstatus"
    )
    risk_level = sa.Enum("LOW", "MEDIUM", "HIGH", name="risklevel")
    policy_decision = sa.Enum("AUTO_APPROVE", "REQUIRE_APPROVAL", "DENY", name="policydecision")
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_request", sa.String(), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("step_count", sa.Integer(), nullable=False),
        sa.Column("conversation_json", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])
    op.create_table(
        "service_states",
        sa.Column("service", sa.String(), nullable=False),
        sa.Column("health", sa.String(), nullable=False),
        sa.Column("restart_count", sa.Integer(), nullable=False),
        sa.Column("last_restart_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("service"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("action_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("payload_json", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_run_id", "audit_events", ["run_id"])
    op.create_index("ix_audit_events_action_id", "audit_events", ["action_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_table(
        "tool_actions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("tool_call_id", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("risk_level", risk_level, nullable=False),
        sa.Column("policy_decision", policy_decision, nullable=False),
        sa.Column("status", action_status, nullable=False),
        sa.Column("arguments_json", sa.String(), nullable=False),
        sa.Column("result_json", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_actions_run_id", "tool_actions", ["run_id"])
    op.create_index("ix_tool_actions_status", "tool_actions", ["status"])
    op.create_index("ix_tool_actions_idempotency_key", "tool_actions", ["idempotency_key"], unique=True)
    op.create_index("ix_tool_actions_created_at", "tool_actions", ["created_at"])


def downgrade() -> None:
    op.drop_table("tool_actions")
    op.drop_table("audit_events")
    op.drop_table("service_states")
    op.drop_table("agent_runs")
    for enum_name in ("policydecision", "risklevel", "actionstatus", "runstatus"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
