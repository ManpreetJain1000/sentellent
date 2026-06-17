from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.checkpoint import reset_checkpointer_cache
from app.core.config import get_settings
from app.core.rate_limit import reset_rate_limiters
from app.db.session import get_db, get_session_factory, reset_session_state
from app.main import create_app
from app.models.organization import Organization
from app.models.user import User
from app.services.auth import AuthService
from app.services.organization import domain_to_org_slug, normalize_email_domain


def create_test_user_token(*, email: str = "agent@example.com", full_name: str = "Test User") -> str:
    db = get_session_factory()()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            email_domain = normalize_email_domain(email)
            org_slug = domain_to_org_slug(email_domain)
            organization = db.scalar(
                select(Organization).where(
                    (Organization.email_domain == email_domain) | (Organization.slug == org_slug)
                )
            )
            if organization is None:
                organization = Organization(
                    name=f"{org_slug} workspace",
                    slug=org_slug,
                    email_domain=email_domain,
                )
                db.add(organization)
                role = "owner"
            else:
                role = "member"
            user = User(
                organization=organization,
                email=email,
                full_name=full_name,
                google_subject=f"test-{uuid4().hex}",
                role=role,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        auth_service = AuthService(settings=get_settings(), db=db)
        token, _ = auth_service.create_session(user)
        return token
    finally:
        db.close()


def _build_alembic_config(database_url: str) -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    alembic_ini = backend_root / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture()
def test_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "sentellent-test.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    os.environ["DATABASE_URL"] = database_url
    os.environ["JWT_SECRET_KEY"] = "test-secret-key"
    os.environ["GROQ_API_KEY"] = ""
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
    os.environ["EMAIL_INGEST_ASYNC_ENABLED"] = "false"
    os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "1000"
    os.environ["RATE_LIMIT_CHAT_PER_MINUTE"] = "1000"
    os.environ["RATE_LIMIT_INGEST_PER_HOUR"] = "1000"
    get_settings.cache_clear()
    reset_checkpointer_cache()
    reset_session_state()
    reset_rate_limiters()

    command.upgrade(_build_alembic_config(database_url), "head")

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


@pytest.fixture()
def db_session(test_client) -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
