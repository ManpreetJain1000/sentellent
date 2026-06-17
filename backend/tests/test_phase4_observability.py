from __future__ import annotations

import pytest

from tests.conftest import create_test_user_token


@pytest.fixture()
def rate_limited_client(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from collections.abc import Generator
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.agent.checkpoint import reset_checkpointer_cache
    from app.core.config import get_settings
    from app.core.rate_limit import reset_rate_limiters
    from app.db.session import get_db, get_session_factory, reset_session_state
    from app.main import create_app
    from sqlalchemy.orm import Session

    database_path = tmp_path / "sentellent-rate-limit.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv("EMAIL_INGEST_ASYNC_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_AUTH_PER_MINUTE", "2")
    monkeypatch.setenv("RATE_LIMIT_CHAT_PER_MINUTE", "1000")
    monkeypatch.setenv("RATE_LIMIT_INGEST_PER_HOUR", "1000")
    get_settings.cache_clear()
    reset_checkpointer_cache()
    reset_session_state()
    reset_rate_limiters()

    backend_root = Path(__file__).resolve().parents[1]
    alembic_ini = backend_root / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        db = get_session_factory()()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    reset_checkpointer_cache()
    reset_session_state()
    reset_rate_limiters()


def test_auth_rate_limit_returns_429(rate_limited_client) -> None:
    first = rate_limited_client.get("/api/v1/auth/google/login")
    second = rate_limited_client.get("/api/v1/auth/google/login")
    third = rate_limited_client.get("/api/v1/auth/google/login")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limit_exceeded"


def test_health_includes_dependency_checks(test_client) -> None:
    response = test_client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert "checks" in payload
    assert payload["checks"]["database"] == "ok"
    assert payload["checks"]["redis"] == "ok"
