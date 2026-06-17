"""phase 3 memory ownership and pgvector embeddings

Revision ID: 0003_phase3_memory
Revises: 0002_workspace_pgvector
Create Date: 2026-06-17 18:00:00.000000
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0003_phase3_memory"
down_revision = "0002_workspace_pgvector"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    columns = inspect(op.get_bind()).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _index_exists(table_name: str, index_name: str) -> bool:
    indexes = inspect(op.get_bind()).get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def _add_memory_columns() -> None:
    if not _column_exists("memory_items", "owner_user_id"):
        op.add_column(
            "memory_items",
            sa.Column("owner_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        )
    if not _column_exists("memory_items", "visibility"):
        op.add_column(
            "memory_items",
            sa.Column("visibility", sa.String(length=32), nullable=False, server_default="private"),
        )
    if not _column_exists("memory_items", "source_kind"):
        op.add_column(
            "memory_items",
            sa.Column("source_kind", sa.String(length=100), nullable=True),
        )
    if not _column_exists("memory_items", "confidence_score"):
        op.add_column(
            "memory_items",
            sa.Column("confidence_score", sa.Float(), nullable=False, server_default="1.0"),
        )
    if not _column_exists("memory_items", "pinned_at"):
        op.add_column("memory_items", sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists("memory_items", "corrected_at"):
        op.add_column("memory_items", sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists("memory_items", "forgotten_at"):
        op.add_column("memory_items", sa.Column("forgotten_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists("memory_items", "source_excerpt"):
        op.add_column("memory_items", sa.Column("source_excerpt", sa.Text(), nullable=True))
    if not _index_exists("memory_items", "ix_memory_items_organization_id_owner_user_id"):
        op.create_index(
            "ix_memory_items_organization_id_owner_user_id",
            "memory_items",
            ["organization_id", "owner_user_id"],
        )
    if not _index_exists("memory_items", "ix_memory_items_organization_id_forgotten_at"):
        op.create_index(
            "ix_memory_items_organization_id_forgotten_at",
            "memory_items",
            ["organization_id", "forgotten_at"],
        )


def _drop_memory_columns() -> None:
    if _index_exists("memory_items", "ix_memory_items_organization_id_forgotten_at"):
        op.drop_index("ix_memory_items_organization_id_forgotten_at", table_name="memory_items")
    if _index_exists("memory_items", "ix_memory_items_organization_id_owner_user_id"):
        op.drop_index("ix_memory_items_organization_id_owner_user_id", table_name="memory_items")
    if _column_exists("memory_items", "source_excerpt"):
        op.drop_column("memory_items", "source_excerpt")
    if _column_exists("memory_items", "forgotten_at"):
        op.drop_column("memory_items", "forgotten_at")
    if _column_exists("memory_items", "corrected_at"):
        op.drop_column("memory_items", "corrected_at")
    if _column_exists("memory_items", "pinned_at"):
        op.drop_column("memory_items", "pinned_at")
    if _column_exists("memory_items", "confidence_score"):
        op.drop_column("memory_items", "confidence_score")
    if _column_exists("memory_items", "source_kind"):
        op.drop_column("memory_items", "source_kind")
    if _column_exists("memory_items", "visibility"):
        op.drop_column("memory_items", "visibility")
    if _column_exists("memory_items", "owner_user_id"):
        op.drop_column("memory_items", "owner_user_id")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if not _table_exists("memory_items"):
        return

    if dialect == "sqlite":
        existing_columns = {column["name"] for column in inspect(bind).get_columns("memory_items")}
        existing_indexes = {index["name"] for index in inspect(bind).get_indexes("memory_items")}
        with op.batch_alter_table("memory_items") as batch_op:
            if "owner_user_id" not in existing_columns:
                batch_op.add_column(sa.Column("owner_user_id", sa.Uuid(as_uuid=True), nullable=True))
            if "visibility" not in existing_columns:
                batch_op.add_column(sa.Column("visibility", sa.String(length=32), nullable=False, server_default="private"))
            if "source_kind" not in existing_columns:
                batch_op.add_column(sa.Column("source_kind", sa.String(length=100), nullable=True))
            if "confidence_score" not in existing_columns:
                batch_op.add_column(sa.Column("confidence_score", sa.Float(), nullable=False, server_default="1.0"))
            if "pinned_at" not in existing_columns:
                batch_op.add_column(sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True))
            if "corrected_at" not in existing_columns:
                batch_op.add_column(sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True))
            if "forgotten_at" not in existing_columns:
                batch_op.add_column(sa.Column("forgotten_at", sa.DateTime(timezone=True), nullable=True))
            if "source_excerpt" not in existing_columns:
                batch_op.add_column(sa.Column("source_excerpt", sa.Text(), nullable=True))
            if "ix_memory_items_organization_id_owner_user_id" not in existing_indexes:
                batch_op.create_index("ix_memory_items_organization_id_owner_user_id", ["organization_id", "owner_user_id"])
            if "ix_memory_items_organization_id_forgotten_at" not in existing_indexes:
                batch_op.create_index("ix_memory_items_organization_id_forgotten_at", ["organization_id", "forgotten_at"])
    else:
        _add_memory_columns()

    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS embedding vector(384)")

        rows = bind.execute(
            sa.text(
                "SELECT id, embedding_vector FROM memory_items WHERE embedding_vector IS NOT NULL"
            )
        ).fetchall()
        for row in rows:
            vector = row.embedding_vector
            if isinstance(vector, str):
                vector = json.loads(vector)
            if not isinstance(vector, list) or not vector:
                continue
            vector_literal = "[" + ",".join(str(float(value)) for value in vector) + "]"
            bind.execute(
                sa.text("UPDATE memory_items SET embedding = CAST(:embedding AS vector) WHERE id = :id"),
                {"embedding": vector_literal, "id": row.id},
            )

        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_memory_items_embedding_hnsw "
            "ON memory_items USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if not _table_exists("memory_items"):
        return

    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_memory_items_embedding_hnsw")
        op.execute("ALTER TABLE memory_items DROP COLUMN IF EXISTS embedding")

    if dialect == "sqlite":
        existing_columns = {column["name"] for column in inspect(bind).get_columns("memory_items")}
        existing_indexes = {index["name"] for index in inspect(bind).get_indexes("memory_items")}
        with op.batch_alter_table("memory_items") as batch_op:
            if "ix_memory_items_organization_id_forgotten_at" in existing_indexes:
                batch_op.drop_index("ix_memory_items_organization_id_forgotten_at")
            if "ix_memory_items_organization_id_owner_user_id" in existing_indexes:
                batch_op.drop_index("ix_memory_items_organization_id_owner_user_id")
            if "source_excerpt" in existing_columns:
                batch_op.drop_column("source_excerpt")
            if "forgotten_at" in existing_columns:
                batch_op.drop_column("forgotten_at")
            if "corrected_at" in existing_columns:
                batch_op.drop_column("corrected_at")
            if "pinned_at" in existing_columns:
                batch_op.drop_column("pinned_at")
            if "confidence_score" in existing_columns:
                batch_op.drop_column("confidence_score")
            if "source_kind" in existing_columns:
                batch_op.drop_column("source_kind")
            if "visibility" in existing_columns:
                batch_op.drop_column("visibility")
            if "owner_user_id" in existing_columns:
                batch_op.drop_column("owner_user_id")
    else:
        _drop_memory_columns()
