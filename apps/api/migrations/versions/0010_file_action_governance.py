"""Add managed workspaces, quarantine entries, and external action metadata."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0010_file_action_governance"
down_revision: str | Sequence[str] | None = "0009_monitoring_mvp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "tool_actions",
        "run_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.add_column(
        "tool_actions",
        sa.Column("proposer_client_id", sa.UUID(), nullable=True),
    )
    op.add_column("tool_actions", sa.Column("target_type", sa.String(length=64), nullable=True))
    op.add_column("tool_actions", sa.Column("target_id", sa.UUID(), nullable=True))
    op.add_column("tool_actions", sa.Column("action_version", sa.String(length=64), nullable=True))
    op.add_column("tool_actions", sa.Column("arguments_digest", sa.String(length=64), nullable=True))
    op.add_column("tool_actions", sa.Column("policy_version", sa.String(length=64), nullable=True))
    op.add_column(
        "tool_actions",
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tool_actions_proposer_client",
        "tool_actions",
        "client_tokens",
        ["proposer_client_id"],
        ["id"],
    )
    op.create_index(
        "ix_tool_actions_proposer_client_id",
        "tool_actions",
        ["proposer_client_id"],
    )
    op.create_index("ix_tool_actions_target_id", "tool_actions", ["target_id"])
    op.create_index(
        "ix_tool_actions_approval_expires_at",
        "tool_actions",
        ["approval_expires_at"],
    )
    op.create_check_constraint(
        "ck_tool_actions_exactly_one_source",
        "tool_actions",
        "(run_id IS NULL) <> (proposer_client_id IS NULL)",
    )

    op.create_table(
        "managed_workspaces",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("root_path", sa.String(length=2048), nullable=False),
        sa.Column("canonical_root_path", sa.String(length=2048), nullable=False),
        sa.Column("quarantine_root_path", sa.String(length=2048), nullable=False),
        sa.Column("protected_patterns", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in {
        "ix_managed_workspaces_name": ["name"],
        "ix_managed_workspaces_enabled": ["enabled"],
        "ix_managed_workspaces_version": ["version"],
        "ix_managed_workspaces_created_at": ["created_at"],
    }.items():
        op.create_index(name, "managed_workspaces", columns)

    op.create_table(
        "quarantine_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("action_id", sa.UUID(), nullable=False),
        sa.Column("original_relative_path", sa.String(length=4000), nullable=False),
        sa.Column("quarantine_relative_path", sa.String(length=4000), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["managed_workspaces.id"]),
        sa.ForeignKeyConstraint(["action_id"], ["tool_actions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('quarantined', 'restored', 'conflict', 'failed')",
            name="ck_quarantine_entries_status",
        ),
    )
    for name, columns in {
        "ix_quarantine_entries_workspace_id": ["workspace_id"],
        "ix_quarantine_entries_action_id": ["action_id"],
        "ix_quarantine_entries_status": ["status"],
        "ix_quarantine_entries_created_at": ["created_at"],
        "ix_quarantine_entries_original_path": ["workspace_id", "original_relative_path"],
    }.items():
        op.create_index(name, "quarantine_entries", columns)


def downgrade() -> None:
    op.drop_table("quarantine_entries")
    op.drop_table("managed_workspaces")
    op.drop_constraint("ck_tool_actions_exactly_one_source", "tool_actions", type_="check")
    op.drop_index("ix_tool_actions_approval_expires_at", table_name="tool_actions")
    op.drop_index("ix_tool_actions_target_id", table_name="tool_actions")
    op.drop_index("ix_tool_actions_proposer_client_id", table_name="tool_actions")
    op.drop_constraint("fk_tool_actions_proposer_client", "tool_actions", type_="foreignkey")
    for column in (
        "approval_expires_at",
        "policy_version",
        "arguments_digest",
        "action_version",
        "target_id",
        "target_type",
        "proposer_client_id",
    ):
        op.drop_column("tool_actions", column)
    op.alter_column(
        "tool_actions",
        "run_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
