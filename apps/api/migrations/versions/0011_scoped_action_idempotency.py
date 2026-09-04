"""Scope external action idempotency keys to the proposer client."""

from collections.abc import Sequence

from alembic import op


revision: str = "0011_scoped_action_idempotency"
down_revision: str | Sequence[str] | None = "0010_file_action_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_tool_actions_idempotency_key", table_name="tool_actions")
    op.create_unique_constraint(
        "uq_tool_actions_client_idempotency",
        "tool_actions",
        ["proposer_client_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_tool_actions_client_idempotency", "tool_actions", type_="unique"
    )
    op.create_index(
        "ix_tool_actions_idempotency_key",
        "tool_actions",
        ["idempotency_key"],
        unique=True,
    )
