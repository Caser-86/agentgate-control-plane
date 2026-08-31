"""Add an ABA-resistant version to control-task leases."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0006_control_task_lease_version"
down_revision: str | Sequence[str] | None = "0005_worker_protocol"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "control_tasks",
        sa.Column("lease_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("control_tasks", "lease_version")
