from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.models.organization import Organization
from app.models.user import User
from app.models.workspace_connection import WorkspaceConnection
from app.schemas.workspace import EmailSummary
from app.services.encryption import TokenEncryptionService
from app.services.jobs import JobService
from tests.conftest import create_test_user_token


@pytest.fixture()
def connected_user(db_session) -> User:
    organization = Organization(
        name="Acme workspace",
        slug="acme-com",
        email_domain="acme.com",
    )
    user = User(
        organization=organization,
        email="owner@acme.com",
        full_name="Owner",
        google_subject=f"google-{uuid4().hex}",
        role="owner",
    )
    db_session.add(organization)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    settings = get_settings()
    encryption = TokenEncryptionService(settings)
    connection = WorkspaceConnection(
        organization_id=user.organization_id,
        user_id=user.id,
        provider="google",
        email=user.email,
        scopes="https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar",
        access_token_encrypted=encryption.encrypt("access-token"),
        refresh_token_encrypted=encryption.encrypt("refresh-token"),
        token_expires_at=datetime.now(timezone.utc),
        is_connected=True,
    )
    db_session.add(connection)
    db_session.commit()
    return user


def test_workspace_ingest_enqueues_job(test_client, connected_user) -> None:
    auth_service_token = create_test_user_token(email=connected_user.email)
    headers = {"Authorization": f"Bearer {auth_service_token}"}

    with patch("app.workers.tasks.email_ingestion.ingest_user_inbox.delay") as mock_delay:
        response = test_client.post("/api/v1/workspace/ingest", headers=headers, json={"max_results": 5})

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_type"] == "email_ingest"
    assert payload["status"] == "pending"
    mock_delay.assert_called_once()


def test_get_job_status_scoped_to_user(test_client, connected_user, db_session) -> None:
    settings = get_settings()
    job_service = JobService(db=db_session, settings=settings)
    with patch("app.workers.tasks.email_ingestion.ingest_user_inbox.delay"):
        job = job_service.enqueue_email_ingest(user=connected_user, max_results=3)

    token = create_test_user_token(email=connected_user.email)
    headers = {"Authorization": f"Bearer {token}"}
    response = test_client.get(f"/api/v1/jobs/{job.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(job.id)


def test_ingest_user_inbox_task_persists_memories(db_session, connected_user) -> None:
    from app.workers.tasks.email_ingestion import ingest_user_inbox

    settings = get_settings()
    job_service = JobService(db=db_session, settings=settings)
    with patch("app.workers.tasks.email_ingestion.ingest_user_inbox.delay"):
        job = job_service.enqueue_email_ingest(user=connected_user, max_results=1)

    sample_email = EmailSummary(
        id="msg-1",
        thread_id="thread-1",
        subject="Project X update",
        sender="pm@example.com",
        snippet="Project X is delayed until next week.",
        received_at=datetime.now(timezone.utc),
    )

    with patch(
        "app.workers.tasks.email_ingestion.GmailService.list_recent_messages",
        new=AsyncMock(return_value=[sample_email]),
    ), patch(
        "app.workers.tasks.email_ingestion.GoogleCredentialsService.get_valid_access_token",
        new=AsyncMock(return_value="access-token"),
    ):
        result = ingest_user_inbox(
            str(job.id),
            str(connected_user.id),
            str(connected_user.organization_id),
            1,
        )

    assert result["memories_created"] >= 1
    db_session.refresh(job)
    assert job.status == "completed"
