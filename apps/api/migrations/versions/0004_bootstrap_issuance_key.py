"""Serialize bootstrap token issuance.

Revision ID: 0004_bootstrap_issuance_key
Revises: 0003_auth_tables
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004_bootstrap_issuance_key"
down_revision: str | Sequence[str] | None = "0003_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bootstrap_tokens",
        sa.Column("issuance_key", sa.String(), nullable=True),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                ROW_NUMBER() OVER (
                    ORDER BY
                        CASE
                            WHEN consumed_at IS NULL AND expires_at > CURRENT_TIMESTAMP THEN 0
                            ELSE 1
                        END,
                        expires_at DESC,
                        created_at DESC,
                        id
                ) AS row_number
            FROM bootstrap_tokens
        )
        UPDATE bootstrap_tokens AS token
        SET issuance_key = CASE
            WHEN ranked.row_number = 1 THEN 'bootstrap'
            ELSE 'legacy-' || token.id::text
        END
        FROM ranked
        WHERE token.id = ranked.id
        """
    )
    op.alter_column("bootstrap_tokens", "issuance_key", nullable=False)
    op.create_index(
        "ix_bootstrap_tokens_issuance_key",
        "bootstrap_tokens",
        ["issuance_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_bootstrap_tokens_issuance_key", table_name="bootstrap_tokens")
    op.drop_column("bootstrap_tokens", "issuance_key")
