"""workspace connections and pgvector extension

Revision ID: 0002_workspace_pgvector
Revises: 0001_initial_schema
Create Date: 2026-06-16 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0002_workspace_pgvector"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    if not _table_exists("workspace_connections"):
        op.create_table(
            "workspace_connections",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "organization_id",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False, server_default=sa.text("'google'")),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("scopes", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("access_token_encrypted", sa.Text(), nullable=True),
            sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
            sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_connected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("organization_id", "user_id", "provider", name="uq_workspace_connections_scope"),
        )


def downgrade() -> None:
    if _table_exists("workspace_connections"):
        op.drop_table("workspace_connections")
