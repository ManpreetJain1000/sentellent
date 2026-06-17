from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EmailSummary:
    id: str
    thread_id: str
    subject: str
    sender: str
    snippet: str
    received_at: datetime | None


@dataclass(frozen=True)
class CalendarEventSummary:
    id: str
    title: str
    start: datetime
    end: datetime
    attendees: list[str]
    location: str | None
    description: str | None


@dataclass(frozen=True)
class CreatedCalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    html_link: str | None
