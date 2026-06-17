from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.models.organization import Organization
from app.models.user import User
from app.models.workspace_connection import WorkspaceConnection
from app.schemas.workspace import CalendarEventSummary
from app.services.calendar import CalendarService
from app.services.encryption import TokenEncryptionService
from app.services.gmail import GmailService
from app.services.memory import MemoryService


@pytest.fixture()
def workspace_user(db_session) -> User:
    organization = Organization(name="Acme workspace", slug=f"acme-{uuid4().hex[:8]}")
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
    return user


@pytest.fixture()
def connected_workspace(db_session, workspace_user) -> WorkspaceConnection:
    settings = get_settings()
    encryption = TokenEncryptionService(settings)
    connection = WorkspaceConnection(
        organization_id=workspace_user.organization_id,
        user_id=workspace_user.id,
        provider="google",
        email=workspace_user.email,
        scopes="https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar",
        access_token_encrypted=encryption.encrypt("access-token"),
        refresh_token_encrypted=encryption.encrypt("refresh-token"),
        token_expires_at=datetime.now(timezone.utc),
        is_connected=True,
    )
    db_session.add(connection)
    db_session.commit()
    db_session.refresh(connection)
    return connection


@pytest.mark.asyncio
async def test_gmail_list_recent_messages_formats_results() -> None:
    gmail = GmailService()
    list_payload = {"messages": [{"id": "msg-1"}]}
    detail_payload = {
        "id": "msg-1",
        "threadId": "thread-1",
        "snippet": "Project X is delayed until next week.",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Project X update"},
                {"name": "From", "value": "pm@example.com"},
                {"name": "Date", "value": "Mon, 16 Jun 2026 10:00:00 +0000"},
            ]
        },
    }

    with patch.object(GmailService, "_request", new_callable=AsyncMock) as mock_request:
        mock_request.side_effect = [list_payload, detail_payload]
        emails = await gmail.list_recent_messages(access_token="token", max_results=1)

    assert len(emails) == 1
    assert emails[0].subject == "Project X update"
    assert "Project X is delayed" in emails[0].snippet


@pytest.mark.asyncio
async def test_calendar_create_event_returns_created_event() -> None:
    calendar = CalendarService()
    response_payload = {
        "id": "evt-1",
        "summary": "Call with Rahul",
        "start": {"dateTime": "2026-06-23T14:00:00Z"},
        "end": {"dateTime": "2026-06-23T14:30:00Z"},
        "htmlLink": "https://calendar.google.com/event?eid=evt-1",
    }

    with patch.object(CalendarService, "_request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = response_payload
        created = await calendar.create_event(
            access_token="token",
            title="Call with Rahul",
            start=datetime(2026, 6, 23, 14, 0),
            end=datetime(2026, 6, 23, 14, 30),
            time_zone="Asia/Kolkata",
            attendees=["rahul@example.com"],
        )

    assert created.id == "evt-1"
    assert created.title == "Call with Rahul"
    assert created.html_link is not None
    call_kwargs = mock_request.call_args.kwargs
    assert call_kwargs["params"]["sendUpdates"] == "all"
    assert call_kwargs["json_body"]["attendees"] == [{"email": "rahul@example.com"}]


@pytest.mark.asyncio
async def test_calendar_create_event_without_attendees_skips_invites() -> None:
    calendar = CalendarService()
    response_payload = {
        "id": "evt-2",
        "summary": "Focus time",
        "start": {"dateTime": "2026-06-23T14:00:00Z"},
        "end": {"dateTime": "2026-06-23T14:30:00Z"},
        "htmlLink": "https://calendar.google.com/event?eid=evt-2",
    }

    with patch.object(CalendarService, "_request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = response_payload
        await calendar.create_event(
            access_token="token",
            title="Focus time",
            start=datetime(2026, 6, 23, 14, 0),
            end=datetime(2026, 6, 23, 14, 30),
            time_zone="Asia/Kolkata",
        )

    call_kwargs = mock_request.call_args.kwargs
    assert call_kwargs["params"]["sendUpdates"] == "none"
    assert "attendees" not in call_kwargs["json_body"]


def test_fetch_recent_emails_persists_email_memory(db_session, workspace_user, connected_workspace) -> None:
    from app.agent.tools import WorkspaceToolContext
    from app.schemas.workspace import EmailSummary

    settings = get_settings()
    memory_service = MemoryService(db=db_session, settings=settings)
    context = WorkspaceToolContext(
        user=workspace_user,
        db=db_session,
        settings=settings,
        memory_service=memory_service,
        conversation_id=uuid4(),
    )

    sample_email = EmailSummary(
        id="msg-1",
        thread_id="thread-1",
        subject="Project X update",
        sender="pm@example.com",
        snippet="Project X is delayed until next week.",
        received_at=datetime.now(timezone.utc),
    )

    with patch(
        "app.agent.tools.GmailService.list_recent_messages",
        new=AsyncMock(return_value=[sample_email]),
    ), patch(
        "app.agent.tools.GoogleCredentialsService.get_valid_access_token",
        new=AsyncMock(return_value="access-token"),
    ):
        summary = context.fetch_recent_emails(max_results=1)

    assert "Project X update" in summary
    assert context.email_memories_persisted >= 1
    items, total = memory_service.list_memories(
        organization_id=workspace_user.organization_id,
        user_id=workspace_user.id,
    )
    assert total >= 1
    assert any("Project X" in item.content for item in items)


def test_memory_extracts_facts_from_email_text() -> None:
    settings = get_settings()
    from app.db.session import get_session_factory

    db = get_session_factory()()
    try:
        memory_service = MemoryService(db=db, settings=settings)
        extracted = memory_service.extract_memories_from_text(
            "Subject: Project X update\nPreview: Project X is delayed until next week.",
            source_hint="email",
        )
        assert any(item["content"] == "Project X is delayed." for item in extracted)
    finally:
        db.close()


def test_list_calendar_events_accepts_string_days_ahead(db_session, workspace_user, connected_workspace) -> None:
    from app.agent.tools import WorkspaceToolContext

    settings = get_settings()
    memory_service = MemoryService(db=db_session, settings=settings)
    context = WorkspaceToolContext(
        user=workspace_user,
        db=db_session,
        settings=settings,
        memory_service=memory_service,
        conversation_id=uuid4(),
    )
    sample_event = CalendarEventSummary(
        id="evt-1",
        title="Meeting with devendra",
        start=datetime(2026, 6, 17, 9, 30, tzinfo=timezone.utc),
        end=datetime(2026, 6, 17, 10, 30, tzinfo=timezone.utc),
        attendees=["devendracode1910@gmail.com"],
        location=None,
        description=None,
    )

    with patch(
        "app.agent.tools.CalendarService.list_events",
        new=AsyncMock(return_value=[sample_event]),
    ), patch(
        "app.agent.tools.CalendarService.get_calendar_timezone",
        new=AsyncMock(return_value="Asia/Kolkata"),
    ), patch(
        "app.agent.tools.GoogleCredentialsService.get_valid_access_token",
        new=AsyncMock(return_value="access-token"),
    ):
        summary = context.list_calendar_events(days_ahead="1")

    assert "id=evt-1" in summary
    assert "Meeting with devendra" in summary
    assert "15:00:00" in summary


def test_delete_calendar_event_by_time(db_session, workspace_user, connected_workspace) -> None:
    from app.agent.tools import WorkspaceToolContext

    settings = get_settings()
    memory_service = MemoryService(db=db_session, settings=settings)
    context = WorkspaceToolContext(
        user=workspace_user,
        db=db_session,
        settings=settings,
        memory_service=memory_service,
        conversation_id=uuid4(),
    )
    sample_event = CalendarEventSummary(
        id="evt-delete",
        title="Meeting with devendra",
        start=datetime(2026, 6, 17, 9, 30, tzinfo=timezone.utc),
        end=datetime(2026, 6, 17, 10, 30, tzinfo=timezone.utc),
        attendees=["devendracode1910@gmail.com"],
        location=None,
        description=None,
    )

    with patch(
        "app.agent.tools.CalendarService.list_events",
        new=AsyncMock(return_value=[sample_event]),
    ), patch(
        "app.agent.tools.CalendarService.get_calendar_timezone",
        new=AsyncMock(return_value="Asia/Kolkata"),
    ), patch(
        "app.agent.tools.CalendarService.delete_event",
        new=AsyncMock(return_value=sample_event),
    ), patch(
        "app.agent.tools.GoogleCredentialsService.get_valid_access_token",
        new=AsyncMock(return_value="access-token"),
    ):
        message = context.delete_calendar_event_by_time(start_local="2026-06-17T15:00:00")

    assert "Deleted calendar event" in message


def test_list_calendar_events_for_date(db_session, workspace_user, connected_workspace) -> None:
    from app.agent.tools import WorkspaceToolContext

    settings = get_settings()
    memory_service = MemoryService(db=db_session, settings=settings)
    context = WorkspaceToolContext(
        user=workspace_user,
        db=db_session,
        settings=settings,
        memory_service=memory_service,
        conversation_id=uuid4(),
    )
    sample_event = CalendarEventSummary(
        id="evt-1",
        title="Meeting with devendra",
        start=datetime(2026, 6, 17, 9, 30, tzinfo=timezone.utc),
        end=datetime(2026, 6, 17, 10, 30, tzinfo=timezone.utc),
        attendees=["devendracode1910@gmail.com"],
        location=None,
        description=None,
    )

    with patch(
        "app.agent.tools.CalendarService.list_events_for_date",
        new=AsyncMock(return_value=[sample_event]),
    ), patch(
        "app.agent.tools.CalendarService.get_calendar_timezone",
        new=AsyncMock(return_value="Asia/Kolkata"),
    ), patch(
        "app.agent.tools.GoogleCredentialsService.get_valid_access_token",
        new=AsyncMock(return_value="access-token"),
    ):
        summary = context.list_calendar_events_for_date("2026-06-17")

    assert "id=evt-1" in summary
    assert "2026-06-17T15:00:00" in summary


def test_create_calendar_event_sends_attendee_invites(
    db_session, workspace_user, connected_workspace
) -> None:
    from app.agent.tools import WorkspaceToolContext
    from app.schemas.workspace import CreatedCalendarEvent

    settings = get_settings()
    memory_service = MemoryService(db=db_session, settings=settings)
    context = WorkspaceToolContext(
        user=workspace_user,
        db=db_session,
        settings=settings,
        memory_service=memory_service,
        conversation_id=uuid4(),
    )
    created = CreatedCalendarEvent(
        id="evt-new",
        title="Meeting with devendra",
        start=datetime(2026, 6, 17, 15, 0),
        end=datetime(2026, 6, 17, 16, 0),
        html_link="https://calendar.google.com/event?eid=evt-new",
    )

    with patch(
        "app.agent.tools.CalendarService.create_event",
        new=AsyncMock(return_value=created),
    ) as mock_create, patch(
        "app.agent.tools.CalendarService.get_calendar_timezone",
        new=AsyncMock(return_value="Asia/Kolkata"),
    ), patch(
        "app.agent.tools.GoogleCredentialsService.get_valid_access_token",
        new=AsyncMock(return_value="access-token"),
    ):
        message = context.create_calendar_event(
            title="Meeting with devendra",
            start_local="2026-06-17T15:00:00",
            end_local="2026-06-17T16:00:00",
            attendees="devendracode1910@gmail.com",
        )

    mock_create.assert_awaited_once()
    assert mock_create.await_args.kwargs["attendees"] == ["devendracode1910@gmail.com"]
    assert "Invitations sent to: devendracode1910@gmail.com" in message
