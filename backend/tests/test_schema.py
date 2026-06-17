from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, inspect
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models import BackgroundJob, Conversation, MemoryItem, Message, Organization, Task, User, WorkspaceConnection


def test_models_define_expected_tables_and_scoping() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert set(inspector.get_table_names()) == {
        "background_jobs",
        "conversations",
        "memory_items",
        "messages",
        "organizations",
        "tasks",
        "users",
        "workspace_connections",
    }

    for model in (Organization, User, Conversation, Message, Task, MemoryItem):
        assert isinstance(model.__table__.c.id.type, Uuid)
        assert model.__table__.c.id.primary_key is True
        assert "created_at" in model.__table__.c
        assert "updated_at" in model.__table__.c
        assert model.__table__.c.created_at.nullable is False
        assert model.__table__.c.updated_at.nullable is False

    for model in (User, Conversation, Message, Task, MemoryItem, BackgroundJob):
        assert "organization_id" in model.__table__.c
        assert model.__table__.c.organization_id.nullable is False

    assert Conversation.__table__.c.expires_at.nullable is False
    assert Conversation.__table__.c.expires_at.type.python_type is datetime
    assert MemoryItem.__table__.c.embedding_vector.nullable is True

    organization_uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("organizations")}
    user_uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("users")}

    assert "uq_organizations_name" in organization_uniques
    assert "uq_organizations_slug" in organization_uniques
    assert "uq_users_organization_email" in user_uniques

    user_fk_targets = {fk["referred_table"] for fk in inspector.get_foreign_keys("users")}
    conversation_fk_targets = {fk["referred_table"] for fk in inspector.get_foreign_keys("conversations")}
    message_fk_targets = {fk["referred_table"] for fk in inspector.get_foreign_keys("messages")}
    task_fk_targets = {fk["referred_table"] for fk in inspector.get_foreign_keys("tasks")}
    memory_fk_targets = {fk["referred_table"] for fk in inspector.get_foreign_keys("memory_items")}

    assert user_fk_targets == {"organizations"}
    assert conversation_fk_targets == {"organizations", "users"}
    assert message_fk_targets == {"organizations", "conversations"}
    assert task_fk_targets == {"organizations", "conversations", "users"}
    assert memory_fk_targets == {"organizations", "conversations", "users"}


def test_models_expose_common_lookup_indexes() -> None:
    index_names = {index.name for index in Conversation.__table__.indexes}
    index_names |= {index.name for index in Message.__table__.indexes}
    index_names |= {index.name for index in Task.__table__.indexes}
    index_names |= {index.name for index in MemoryItem.__table__.indexes}

    assert "ix_conversations_organization_id_created_at" in index_names
    assert "ix_messages_conversation_id_created_at" in index_names
    assert "ix_tasks_organization_id_status" in index_names
    assert "ix_memory_items_organization_id_memory_type" in index_names
