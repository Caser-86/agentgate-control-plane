"""Add native Worker protocol state.

Revision ID: 0005_worker_protocol
Revises: 0004_bootstrap_issuance_key
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_worker_protocol"
down_revision: str | Sequence[str] | None = "0004_bootstrap_issuance_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "worker_registrations",
        sa.Column("protocol_version", sa.String(), nullable=False, server_default="1.0"),
    )
    op.create_table(
        "worker_execution_grants",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("worker_id", sa.UUID(), nullable=False),
        sa.Column("request_digest", sa.String(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["control_tasks.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["worker_registrations.id"]),
        sa.PrimaryKeyConstraint("task_id"),
    )
    for name, columns in {
        "ix_worker_execution_grants_worker_id": ["worker_id"],
        "ix_worker_execution_grants_request_digest": ["request_digest"],
        "ix_worker_execution_grants_lease_expires_at": ["lease_expires_at"],
        "ix_worker_execution_grants_started_at": ["started_at"],
        "ix_worker_execution_grants_completed_at": ["completed_at"],
    }.items():
        op.create_index(name, "worker_execution_grants", columns)


def downgrade() -> None:
    op.drop_table("worker_execution_grants")
    op.drop_column("worker_registrations", "protocol_version")
