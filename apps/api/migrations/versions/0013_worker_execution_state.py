"""Persist the native Worker execution state reported with heartbeats.

Revision ID: 0013_worker_execution_state
Revises: 0012_partial_action_idempotency
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_worker_execution_state"
down_revision: str | Sequence[str] | None = "0012_partial_action_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "worker_registrations",
        sa.Column("execution_status", sa.String(length=32), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "worker_registrations",
        sa.Column("pending_report_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "worker_registrations",
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("worker_registrations", "last_error_code")
    op.drop_column("worker_registrations", "pending_report_count")
    op.drop_column("worker_registrations", "execution_status")
