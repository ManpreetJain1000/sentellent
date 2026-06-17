from __future__ import annotations

from uuid import uuid4

from app.agent.checkpoint import build_checkpoint_config, get_checkpointer
from app.core.config import get_settings


def test_checkpoint_config_is_stable_per_conversation() -> None:
    organization_id = uuid4()
    user_id = uuid4()
    conversation_id = uuid4()

    first = build_checkpoint_config(
        organization_id=organization_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    second = build_checkpoint_config(
        organization_id=organization_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )

    assert first == second
    assert first["configurable"]["thread_id"] == str(conversation_id)
    assert first["configurable"]["checkpoint_ns"] == f"org/{organization_id}/user/{user_id}"


def test_checkpointer_uses_in_memory_saver_for_sqlite() -> None:
    settings = get_settings()
    checkpointer = get_checkpointer("sqlite+pysqlite:///:memory:")
    assert checkpointer.__class__.__name__ in {"InMemorySaver", "MemorySaver"}


def test_checkpointer_delete_thread_is_safe_for_sqlite() -> None:
    settings = get_settings()
    checkpointer = get_checkpointer("sqlite+pysqlite:///:memory:")
    thread_id = str(uuid4())
    checkpointer.delete_thread(thread_id)
