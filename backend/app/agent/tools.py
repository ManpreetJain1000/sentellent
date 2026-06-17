from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models.user import User
from app.models.workspace_connection import WorkspaceConnection
from app.services.auth import AuthService
from app.services.calendar import CalendarService
from app.services.gmail import GmailService
from app.services.google_credentials import GoogleCredentialsService
from app.services.google_scopes import has_gmail_access, missing_calendar_scopes
from app.services.memory import MemoryService
from app.services.timezone_utils import (
    format_local_datetime,
    parse_local_datetime,
    to_local_naive,
)


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


class FetchRecentEmailsInput(BaseModel):
    max_results: str = Field(default="10", description="Number of emails to fetch, as a string e.g. '10'.")

    @field_validator("max_results", mode="before")
    @classmethod
    def coerce_max_results(cls, value: object) -> str:
        return str(value) if value is not None else "10"


class ListCalendarEventsInput(BaseModel):
    days_ahead: str = Field(default="7", description="Days ahead to search, as a string e.g. '1' or '7'.")

    @field_validator("days_ahead", mode="before")
    @classmethod
    def coerce_days_ahead(cls, value: object) -> str:
        return str(value) if value is not None else "7"


class ListCalendarEventsForDateInput(BaseModel):
    date_local: str = Field(
        description="Calendar date as YYYY-MM-DD in the user's local timezone. Example: 2026-06-17 for tomorrow."
    )


class CreateCalendarEventInput(BaseModel):
    """Local-time fields for Groq tool-calling (do not use UTC/Z suffix)."""

    title: str = Field(description="Event title.")
    start_local: str = Field(
        description="Start in the user's local timezone as YYYY-MM-DDTHH:MM:SS (no Z). Example: 2026-06-17T15:00:00 for 3 PM."
    )
    end_local: str = Field(
        description="End in the user's local timezone as YYYY-MM-DDTHH:MM:SS (no Z). Example: 2026-06-17T16:00:00 for 4 PM."
    )
    attendees: str = Field(
        default="",
        description=(
            "Comma-separated invitee email addresses. Required when scheduling with others so they receive "
            "a Google Calendar invitation. Example: alice@example.com,bob@example.com. Use empty string for solo events."
        ),
    )

    @field_validator("attendees", mode="before")
    @classmethod
    def coerce_attendees(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)


class DeleteCalendarEventInput(BaseModel):
    event_id: str = Field(description="Google Calendar event ID from list_calendar_events (id=...).")


class DeleteCalendarEventByTimeInput(BaseModel):
    start_local: str = Field(
        description="Local start time of the event to delete, YYYY-MM-DDTHH:MM:SS. Example: 2026-06-17T20:30:00 for 8:30 PM."
    )
    title_contains: str = Field(
        default="",
        description="Optional substring to match the event title. Use empty string if not needed.",
    )

    @field_validator("title_contains", mode="before")
    @classmethod
    def coerce_title_contains(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)


def _parse_attendee_emails(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_bounded_int(value: str, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _same_local_minute(left: datetime, right: datetime) -> bool:
    return (left.year, left.month, left.day, left.hour, left.minute) == (
        right.year,
        right.month,
        right.day,
        right.hour,
        right.minute,
    )


def _same_local_day(left: datetime, right: datetime) -> bool:
    return (left.year, left.month, left.day) == (right.year, right.month, right.day)


def _tool_error(message: str) -> str:
    return message


class WorkspaceToolContext:
    def __init__(
        self,
        *,
        user: User,
        db: Session,
        settings: Settings,
        memory_service: MemoryService,
        conversation_id: UUID,
    ) -> None:
        self.user = user
        self.db = db
        self.settings = settings
        self.memory_service = memory_service
        self.conversation_id = conversation_id
        self.auth_service = AuthService(settings=settings, db=db)
        self.credentials = GoogleCredentialsService(settings=settings, db=db)
        self.gmail = GmailService()
        self.calendar = CalendarService()
        self.email_memories_persisted = 0

    def _get_connection(self) -> WorkspaceConnection:
        connection = self.auth_service.get_workspace_connection(self.user)
        if connection is None or not connection.is_connected:
            raise AppError(
                "Google Workspace is not connected.",
                code="workspace_not_connected",
                status_code=400,
            )
        return connection

    def _ensure_gmail_scope(self, connection: WorkspaceConnection) -> None:
        if not has_gmail_access(connection.scopes):
            raise AppError(
                "Gmail permission was not granted. Open /api/v1/auth/google/reconnect, approve Gmail access, "
                "then try again.",
                code="gmail_scope_missing",
                status_code=403,
            )

    def _ensure_calendar_scope(self, connection: WorkspaceConnection, *, require_write: bool = False) -> None:
        missing = missing_calendar_scopes(connection.scopes, require_write=require_write)
        if missing:
            raise AppError(
                "Google Calendar permission was not granted. Log out, visit /api/v1/auth/google/reconnect, "
                "approve Calendar access on the consent screen, then try again.",
                code="calendar_scope_missing",
                status_code=403,
                details={"missing_scopes": missing},
            )

    def fetch_recent_emails(self, max_results: str = "10") -> str:
        connection = self._get_connection()
        self._ensure_gmail_scope(connection)
        limit = _parse_bounded_int(max_results, default=10, minimum=1, maximum=25)

        if self.settings.email_ingest_async_enabled:
            from app.services.jobs import JobService

            job = JobService(db=self.db, settings=self.settings).enqueue_email_ingest(
                user=self.user,
                max_results=limit,
            )
            return (
                f"Processing inbox in the background (job {job.id}). "
                "Recent email facts will appear in memory shortly."
            )

        async def _fetch() -> str:
            access_token = await self.credentials.get_valid_access_token(connection)
            emails = await self.gmail.list_recent_messages(access_token=access_token, max_results=limit)
            for email_item in emails:
                extracted = self.memory_service.extract_memories_from_text(
                    GmailService.memory_source_text(email_item),
                    source_hint="email",
                )
                for memory in extracted:
                    self.memory_service.create_memory(
                        organization_id=self.user.organization_id,
                        owner_user_id=self.user.id,
                        conversation_id=self.conversation_id,
                        content=memory["content"],
                        memory_type=memory["memory_type"],
                        source_type="email",
                        source_ref=email_item.id,
                    )
                    self.email_memories_persisted += 1
            return GmailService.format_summaries(emails)

        return _run_async(_fetch())

    async def _calendar_timezone(self, access_token: str) -> str:
        return await self.calendar.get_calendar_timezone(
            access_token=access_token,
            fallback=self.settings.default_timezone,
        )

    def list_calendar_events(self, days_ahead: str = "7") -> str:
        connection = self._get_connection()
        self._ensure_calendar_scope(connection)
        days = _parse_bounded_int(days_ahead, default=7, minimum=1, maximum=30)

        async def _list() -> str:
            access_token = await self.credentials.get_valid_access_token(connection)
            time_zone = await self._calendar_timezone(access_token)
            events = await self.calendar.list_events(
                access_token=access_token,
                days_ahead=days,
                days_back=1,
            )
            return CalendarService.format_events(events, timezone_name=time_zone)

        return _run_async(_list())

    def list_calendar_events_for_date(self, date_local: str) -> str:
        connection = self._get_connection()
        self._ensure_calendar_scope(connection)

        async def _list() -> str:
            access_token = await self.credentials.get_valid_access_token(connection)
            time_zone = await self._calendar_timezone(access_token)
            events = await self.calendar.list_events_for_date(
                access_token=access_token,
                date_local=date_local,
                timezone_name=time_zone,
            )
            if not events:
                return f"No calendar events found on {date_local} ({time_zone})."
            return CalendarService.format_events(events, timezone_name=time_zone)

        return _run_async(_list())

    def delete_calendar_event(self, event_id: str) -> str:
        connection = self._get_connection()
        self._ensure_calendar_scope(connection, require_write=True)

        async def _delete() -> str:
            try:
                access_token = await self.credentials.get_valid_access_token(connection)
                deleted = await self.calendar.delete_event(access_token=access_token, event_id=event_id.strip())
            except AppError as exc:
                return _tool_error(exc.message)
            return f"Deleted calendar event '{deleted.title}' (id={deleted.id})."

        return _run_async(_delete())

    def delete_calendar_event_by_time(self, start_local: str, title_contains: str = "") -> str:
        connection = self._get_connection()
        self._ensure_calendar_scope(connection, require_write=True)
        target_start = parse_local_datetime(start_local)
        title_filter = title_contains.strip().lower()

        async def _delete_by_time() -> str:
            try:
                access_token = await self.credentials.get_valid_access_token(connection)
                time_zone = await self._calendar_timezone(access_token)
                events = await self.calendar.list_events(
                    access_token=access_token,
                    days_ahead=14,
                    days_back=7,
                )
                matches = []
                for event in events:
                    event_start = to_local_naive(event.start, time_zone)
                    if not _same_local_minute(event_start, target_start):
                        continue
                    if title_filter and title_filter not in event.title.lower():
                        continue
                    matches.append(event)

                if not matches:
                    same_day = [
                        event
                        for event in events
                        if _same_local_day(to_local_naive(event.start, time_zone), target_start)
                    ]
                    if title_filter:
                        matches = [event for event in same_day if title_filter in event.title.lower()]
                    elif len(same_day) == 1:
                        matches = same_day

                if not matches:
                    preview = CalendarService.format_events(
                        same_day or events[:5],
                        timezone_name=time_zone,
                    )
                    return _tool_error(
                        f"No event at {format_local_datetime(target_start)} ({time_zone}). "
                        f"Calendar shows:\n{preview}"
                    )
                if len(matches) > 1:
                    options = "; ".join(
                        f"{item.title} at {format_local_datetime(to_local_naive(item.start, time_zone))} (id={item.id})"
                        for item in matches
                    )
                    return _tool_error(
                        f"Multiple events match. Ask the user which one to delete, or use delete_calendar_event with an id. Matches: {options}"
                    )

                deleted = await self.calendar.delete_event(access_token=access_token, event_id=matches[0].id)
                deleted_start = format_local_datetime(to_local_naive(deleted.start, time_zone))
                return f"Deleted calendar event '{deleted.title}' scheduled at {deleted_start} ({time_zone})."
            except AppError as exc:
                return _tool_error(exc.message)

        return _run_async(_delete_by_time())

    def create_calendar_event(
        self,
        title: str,
        start_local: str,
        end_local: str,
        attendees: str = "",
    ) -> str:
        connection = self._get_connection()
        self._ensure_calendar_scope(connection, require_write=True)
        start = parse_local_datetime(start_local)
        end = parse_local_datetime(end_local)
        attendee_emails = _parse_attendee_emails(attendees)

        async def _create() -> str:
            access_token = await self.credentials.get_valid_access_token(connection)
            time_zone = await self.calendar.get_calendar_timezone(
                access_token=access_token,
                fallback=self.settings.default_timezone,
            )
            created = await self.calendar.create_event(
                access_token=access_token,
                title=title,
                start=start,
                end=end,
                time_zone=time_zone,
                attendees=attendee_emails or None,
            )
            local_start = format_local_datetime(start)
            local_end = format_local_datetime(end)
            attendee_text = ", ".join(attendee_emails) if attendee_emails else "none"
            self.memory_service.create_memory(
                organization_id=self.user.organization_id,
                owner_user_id=self.user.id,
                conversation_id=self.conversation_id,
                content=(
                    f"Scheduled '{created.title}' on {local_start} to {local_end} "
                    f"({time_zone} local time) with attendees: {attendee_text}."
                ),
                memory_type="context",
                source_type="calendar",
                source_ref=created.id,
            )
            link_text = f" Link: {created.html_link}" if created.html_link else ""
            invite_text = (
                f" Invitations sent to: {attendee_text}."
                if attendee_emails
                else ""
            )
            return (
                f"Created calendar event '{created.title}' "
                f"from {local_start} to {local_end} ({time_zone}).{invite_text}{link_text}"
            )

        return _run_async(_create())


def build_workspace_tools(context: WorkspaceToolContext) -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            name="fetch_recent_emails",
            description=(
                "Fetch recent Gmail inbox messages for the connected user. "
                "Use when the user asks about inbox priorities, unread mail, or email summaries. "
                "Automatically extracts important facts into long-term memory."
            ),
            func=lambda max_results="10": context.fetch_recent_emails(max_results=max_results),
            args_schema=FetchRecentEmailsInput,
        ),
        StructuredTool.from_function(
            name="list_calendar_events_for_date",
            description=(
                "List all Google Calendar events on a specific local date (YYYY-MM-DD). "
                "Use for 'what's on my calendar tomorrow' or a specific day."
            ),
            func=context.list_calendar_events_for_date,
            args_schema=ListCalendarEventsForDateInput,
        ),
        StructuredTool.from_function(
            name="list_calendar_events",
            description=(
                "List Google Calendar events for the next N days (includes id=... and local times). "
                "Always use this before delete — do not rely on memory alone."
            ),
            func=lambda days_ahead="7": context.list_calendar_events(days_ahead=days_ahead),
            args_schema=ListCalendarEventsInput,
        ),
        StructuredTool.from_function(
            name="delete_calendar_event",
            description=(
                "Delete a Google Calendar event by event id from list_calendar_events. "
                "Use when you already have the id= value."
            ),
            func=context.delete_calendar_event,
            args_schema=DeleteCalendarEventInput,
        ),
        StructuredTool.from_function(
            name="delete_calendar_event_by_time",
            description=(
                "Delete a calendar event by local start time. "
                "Always list_calendar_events_for_date first to get the exact local time. "
                "If user says 8:30 PM but calendar shows 3 PM, use the time from the list tool. "
                "Optional title_contains helps disambiguate, e.g. 'devendra'."
            ),
            func=context.delete_calendar_event_by_time,
            args_schema=DeleteCalendarEventByTimeInput,
        ),
        StructuredTool.from_function(
            name="create_calendar_event",
            description=(
                "Create a Google Calendar event using the user's LOCAL timezone. "
                "Required: title, start_local, end_local as YYYY-MM-DDTHH:MM:SS without Z. "
                "If user says 3 PM, use T15:00:00 local time, NOT UTC. "
                "When scheduling with someone else, ALWAYS pass their email in attendees "
                "(comma-separated) so they receive a calendar invitation. "
                "Respect stored scheduling preferences such as avoiding 9 AM meetings."
            ),
            func=context.create_calendar_event,
            args_schema=CreateCalendarEventInput,
        ),
    ]
