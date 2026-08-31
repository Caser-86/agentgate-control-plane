"""Bind native execution grants and proposed checks to lease/submitter."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007_bound_grants_check_owner"
down_revision: str | Sequence[str] | None = "0006_control_task_lease_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "worker_execution_grants",
        sa.Column("lease_version", sa.Integer(), nullable=False, server_default="0"),
    )
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("control_tasks") as batch:
            batch.add_column(sa.Column("proposer_client_id", sa.UUID(), nullable=True))
            batch.create_foreign_key(
                "fk_control_tasks_proposer_client_id", "client_tokens",
                ["proposer_client_id"], ["id"],
            )
            batch.drop_constraint("uq_control_tasks_idempotency_key", type_="unique")
    else:
        op.add_column("control_tasks", sa.Column("proposer_client_id", sa.UUID(), nullable=True))
        op.create_foreign_key(
            "fk_control_tasks_proposer_client_id", "control_tasks", "client_tokens",
            ["proposer_client_id"], ["id"],
        )
        op.drop_constraint("uq_control_tasks_idempotency_key", "control_tasks", type_="unique")
    op.create_index(
        "ix_control_tasks_proposer_client_id", "control_tasks", ["proposer_client_id"]
    )
    op.create_index(
        "uq_control_tasks_proposer_idempotency", "control_tasks",
        ["proposer_client_id", "idempotency_key"], unique=True,
        postgresql_where=sa.text("proposer_client_id IS NOT NULL"),
        sqlite_where=sa.text("proposer_client_id IS NOT NULL"),
    )
    op.create_index(
        "uq_control_tasks_internal_idempotency", "control_tasks", ["idempotency_key"],
        unique=True, postgresql_where=sa.text("proposer_client_id IS NULL"),
        sqlite_where=sa.text("proposer_client_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_control_tasks_proposer_idempotency", table_name="control_tasks")
    op.drop_index("uq_control_tasks_internal_idempotency", table_name="control_tasks")
    op.create_unique_constraint(
        "uq_control_tasks_idempotency_key", "control_tasks", ["idempotency_key"]
    )
    op.drop_index("ix_control_tasks_proposer_client_id", table_name="control_tasks")
    op.drop_constraint("fk_control_tasks_proposer_client_id", "control_tasks", type_="foreignkey")
    op.drop_column("control_tasks", "proposer_client_id")
    op.drop_column("worker_execution_grants", "lease_version")
