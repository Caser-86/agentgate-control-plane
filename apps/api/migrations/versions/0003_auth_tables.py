"""Add local operator authentication tables.

Revision ID: 0003_auth_tables
Revises: 0002_control_plane_tables
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_auth_tables"
down_revision: str | Sequence[str] | None = "0002_control_plane_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operators_created_at", "operators", ["created_at"])

    op.create_table(
        "web_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("operator_id", sa.UUID(), nullable=False),
        sa.Column("token_digest", sa.String(), nullable=False),
        sa.Column("csrf_digest", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["operator_id"], ["operators.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest", name="uq_web_sessions_token_digest"),
    )
    for name, columns in {
        "ix_web_sessions_operator_id": ["operator_id"],
        "ix_web_sessions_token_digest": ["token_digest"],
        "ix_web_sessions_expires_at": ["expires_at"],
        "ix_web_sessions_revoked_at": ["revoked_at"],
        "ix_web_sessions_created_at": ["created_at"],
    }.items():
        op.create_index(name, "web_sessions", columns)

    op.create_table(
        "client_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("token_digest", sa.String(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest", name="uq_client_tokens_token_digest"),
    )
    for name, columns in {
        "ix_client_tokens_name": ["name"],
        "ix_client_tokens_token_digest": ["token_digest"],
        "ix_client_tokens_expires_at": ["expires_at"],
        "ix_client_tokens_revoked_at": ["revoked_at"],
        "ix_client_tokens_created_at": ["created_at"],
    }.items():
        op.create_index(name, "client_tokens", columns)

    op.create_table(
        "bootstrap_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("token_digest", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest", name="uq_bootstrap_tokens_token_digest"),
    )
    for name, columns in {
        "ix_bootstrap_tokens_token_digest": ["token_digest"],
        "ix_bootstrap_tokens_expires_at": ["expires_at"],
        "ix_bootstrap_tokens_consumed_at": ["consumed_at"],
        "ix_bootstrap_tokens_created_at": ["created_at"],
    }.items():
        op.create_index(name, "bootstrap_tokens", columns)


def downgrade() -> None:
    op.drop_table("bootstrap_tokens")
    op.drop_table("client_tokens")
    op.drop_table("web_sessions")
    op.drop_table("operators")
