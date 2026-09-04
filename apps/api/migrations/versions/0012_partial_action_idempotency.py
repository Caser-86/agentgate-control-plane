"""Keep legacy action keys unique while scoping external keys per client."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_partial_action_idempotency"
down_revision: str | Sequence[str] | None = "0011_scoped_action_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_tool_actions_client_idempotency", "tool_actions", type_="unique")
    op.create_index(
        "uq_tool_actions_legacy_idempotency",
        "tool_actions",
        ["idempotency_key"],
        unique=True,
        sqlite_where=sa.text("proposer_client_id IS NULL"),
        postgresql_where=sa.text("proposer_client_id IS NULL"),
    )
    op.create_index(
        "uq_tool_actions_client_idempotency",
        "tool_actions",
        ["proposer_client_id", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text("proposer_client_id IS NOT NULL"),
        postgresql_where=sa.text("proposer_client_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_tool_actions_client_idempotency", table_name="tool_actions")
    op.drop_index("uq_tool_actions_legacy_idempotency", table_name="tool_actions")
    op.create_unique_constraint(
        "uq_tool_actions_client_idempotency",
        "tool_actions",
        ["proposer_client_id", "idempotency_key"],
    )
