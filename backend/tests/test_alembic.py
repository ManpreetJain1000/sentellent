from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def _build_alembic_config(database_url: str) -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    alembic_ini = backend_root / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_alembic_upgrade_and_downgrade_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "sentellent.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    config = _build_alembic_config(database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables_after_upgrade = set(inspector.get_table_names())

    assert {
        "alembic_version",
        "conversations",
        "memory_items",
        "messages",
        "organizations",
        "tasks",
        "users",
        "workspace_connections",
    }.issubset(tables_after_upgrade)

    command.downgrade(config, "base")

    inspector = inspect(engine)
    tables_after_downgrade = set(inspector.get_table_names())

    assert "conversations" not in tables_after_downgrade
    assert "memory_items" not in tables_after_downgrade
    assert "messages" not in tables_after_downgrade
    assert "organizations" not in tables_after_downgrade
    assert "tasks" not in tables_after_downgrade
    assert "users" not in tables_after_downgrade
