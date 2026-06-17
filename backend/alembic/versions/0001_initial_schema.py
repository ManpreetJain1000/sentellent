"""initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-06-16 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    indexes = inspect(op.get_bind()).get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def upgrade() -> None:
    if not _table_exists("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("name", name="uq_organizations_name"),
            sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        )

    if not _table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "organization_id",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=True),
            sa.Column("google_subject", sa.String(length=255), nullable=True),
            sa.Column("role", sa.String(length=50), nullable=False, server_default=sa.text("'member'")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("organization_id", "email", name="uq_users_organization_email"),
        )

    if not _table_exists("conversations"):
        op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'active'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if not _table_exists("messages"):
        op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if not _table_exists("tasks"):
        op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assigned_to_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'open'")),
        sa.Column("priority", sa.String(length=50), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if not _table_exists("memory_items"):
        op.create_table(
        "memory_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("memory_type", sa.String(length=100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding_vector", sa.JSON(), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if _table_exists("conversations") and not _index_exists("conversations", "ix_conversations_organization_id_created_at"):
        op.create_index("ix_conversations_organization_id_created_at", "conversations", ["organization_id", "created_at"])
    if _table_exists("conversations") and not _index_exists("conversations", "ix_conversations_organization_id_expires_at"):
        op.create_index("ix_conversations_organization_id_expires_at", "conversations", ["organization_id", "expires_at"])
    if _table_exists("messages") and not _index_exists("messages", "ix_messages_conversation_id_created_at"):
        op.create_index("ix_messages_conversation_id_created_at", "messages", ["conversation_id", "created_at"])
    if _table_exists("messages") and not _index_exists("messages", "ix_messages_organization_id_created_at"):
        op.create_index("ix_messages_organization_id_created_at", "messages", ["organization_id", "created_at"])
    if _table_exists("tasks") and not _index_exists("tasks", "ix_tasks_organization_id_status"):
        op.create_index("ix_tasks_organization_id_status", "tasks", ["organization_id", "status"])
    if _table_exists("tasks") and not _index_exists("tasks", "ix_tasks_organization_id_due_at"):
        op.create_index("ix_tasks_organization_id_due_at", "tasks", ["organization_id", "due_at"])
    if _table_exists("memory_items") and not _index_exists("memory_items", "ix_memory_items_organization_id_memory_type"):
        op.create_index("ix_memory_items_organization_id_memory_type", "memory_items", ["organization_id", "memory_type"])
    if _table_exists("memory_items") and not _index_exists("memory_items", "ix_memory_items_organization_id_source_type"):
        op.create_index("ix_memory_items_organization_id_source_type", "memory_items", ["organization_id", "source_type"])


def downgrade() -> None:
    if _table_exists("memory_items") and _index_exists("memory_items", "ix_memory_items_organization_id_source_type"):
        op.drop_index("ix_memory_items_organization_id_source_type", table_name="memory_items")
    if _table_exists("memory_items") and _index_exists("memory_items", "ix_memory_items_organization_id_memory_type"):
        op.drop_index("ix_memory_items_organization_id_memory_type", table_name="memory_items")
    if _table_exists("tasks") and _index_exists("tasks", "ix_tasks_organization_id_due_at"):
        op.drop_index("ix_tasks_organization_id_due_at", table_name="tasks")
    if _table_exists("tasks") and _index_exists("tasks", "ix_tasks_organization_id_status"):
        op.drop_index("ix_tasks_organization_id_status", table_name="tasks")
    if _table_exists("messages") and _index_exists("messages", "ix_messages_organization_id_created_at"):
        op.drop_index("ix_messages_organization_id_created_at", table_name="messages")
    if _table_exists("messages") and _index_exists("messages", "ix_messages_conversation_id_created_at"):
        op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    if _table_exists("conversations") and _index_exists("conversations", "ix_conversations_organization_id_expires_at"):
        op.drop_index("ix_conversations_organization_id_expires_at", table_name="conversations")
    if _table_exists("conversations") and _index_exists("conversations", "ix_conversations_organization_id_created_at"):
        op.drop_index("ix_conversations_organization_id_created_at", table_name="conversations")
    if _table_exists("memory_items"):
        op.drop_table("memory_items")
    if _table_exists("tasks"):
        op.drop_table("tasks")
    if _table_exists("messages"):
        op.drop_table("messages")
    if _table_exists("conversations"):
        op.drop_table("conversations")
    if _table_exists("users"):
        op.drop_table("users")
    if _table_exists("organizations"):
        op.drop_table("organizations")
