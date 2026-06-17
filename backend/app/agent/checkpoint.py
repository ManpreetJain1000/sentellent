from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.core.config import Settings, get_settings

_checkpoint_schema_ready = False


def build_checkpoint_config(
    *,
    organization_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
) -> dict[str, dict[str, str]]:
    return {
        "configurable": {
            "thread_id": str(conversation_id),
            "checkpoint_ns": f"org/{organization_id}/user/{user_id}",
        }
    }


def _normalize_psycopg_conn_string(database_url: str) -> str:
    return (
        database_url.replace("postgresql+psycopg://", "postgresql://")
        .replace("postgres+psycopg://", "postgresql://")
    )


def _connection_kwargs(database_url: str) -> dict[str, str]:
    settings = get_settings()
    if database_url.startswith("sqlite"):
        return {}
    return dict(settings.database_connect_args)


def ensure_checkpoint_schema(database_url: str) -> None:
    """Run LangGraph checkpoint DDL outside a transaction (required for CONCURRENTLY indexes)."""
    global _checkpoint_schema_ready
    if _checkpoint_schema_ready or database_url.startswith("sqlite"):
        return

    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg import Connection

    conn_string = _normalize_psycopg_conn_string(database_url)
    conn_kwargs = _connection_kwargs(database_url)
    with Connection.connect(
        conn_string,
        autocommit=True,
        prepare_threshold=0,
        **conn_kwargs,
    ) as conn:
        PostgresSaver(conn).setup()
    _checkpoint_schema_ready = True


@lru_cache(maxsize=1)
def get_checkpointer(database_url: str) -> BaseCheckpointSaver:
    if database_url.startswith("sqlite"):
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver()

    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    conn_string = _normalize_psycopg_conn_string(database_url)
    conn_kwargs = _connection_kwargs(database_url)
    ensure_checkpoint_schema(database_url)
    pool = ConnectionPool(conninfo=conn_string, kwargs=conn_kwargs, max_size=5, open=True)
    return PostgresSaver(pool)


def delete_conversation_checkpoint(*, settings: Settings, conversation_id: UUID) -> None:
    checkpointer = get_checkpointer(settings.sqlalchemy_database_url)
    if hasattr(checkpointer, "delete_thread"):
        checkpointer.delete_thread(str(conversation_id))


def reset_checkpointer_cache() -> None:
    global _checkpoint_schema_ready
    _checkpoint_schema_ready = False
    get_checkpointer.cache_clear()
