"""Serialize operator installation.

Revision ID: 0008_operator_installation_key
Revises: 0007_bound_grants_check_owner
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_operator_installation_key"
down_revision: str | Sequence[str] | None = "0007_bound_grants_check_owner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF (SELECT COUNT(*) FROM operators) > 1 THEN
                RAISE EXCEPTION
                    'operator installation migration aborted: multiple historical operators exist';
            END IF;
        END $$;
        """
    )

    op.add_column(
        "operators",
        sa.Column("installation_key", sa.String(), nullable=True),
    )
    op.execute("UPDATE operators SET installation_key = 'operator'")
    op.alter_column(
        "operators",
        "installation_key",
        existing_type=sa.String(),
        nullable=False,
    )
    op.create_index(
        "ix_operators_installation_key",
        "operators",
        ["installation_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_operators_installation_key", table_name="operators")
    op.drop_column("operators", "installation_key")
