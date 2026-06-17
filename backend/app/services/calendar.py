from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app.core.exceptions import AppError
from app.services.timezone_utils import (
    day_bounds,
    format_local_datetime,
    parse_local_date,
    parse_local_datetime,
    to_local_naive,
)
from app.schemas.workspace import CalendarEventSummary, CreatedCalendarEvent

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary"
CALENDAR_SETTINGS_TIMEZONE = "https://www.googleapis.com/calendar/v3/users/me/settings/timezone"


class CalendarService:
    def __init__(self, *, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    async def list_upcoming_events(
        self,
        *,
        access_token: str,
        days_ahead: int = 7,
        max_results: int = 20,
    ) -> list[CalendarEventSummary]:
        return await self.list_events(
            access_token=access_token,
            days_ahead=days_ahead,
            days_back=0,
            max_results=max_results,
        )

    async def list_events(
        self,
        *,
        access_token: str,
        days_ahead: int = 7,
        days_back: int = 1,
        max_results: int = 50,
    ) -> list[CalendarEventSummary]:
        now = datetime.now(timezone.utc)
        time_min = now - timedelta(days=max(0, min(days_back, 30)))
        time_max = now + timedelta(days=max(1, min(days_ahead, 30)))
        params = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": max(1, min(max_results, 50)),
        }
        payload = await self._request(
            access_token=access_token,
            method="GET",
            url=f"{CALENDAR_API_BASE}/events",
            params=params,
        )
        return self._parse_event_items(payload.get("items", []))

    async def list_events_for_date(
        self,
        *,
        access_token: str,
        date_local: str,
        timezone_name: str,
        max_results: int = 50,
    ) -> list[CalendarEventSummary]:
        day = parse_local_date(date_local)
        time_min, time_max = day_bounds(timezone_name, day)
        params = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": max(1, min(max_results, 50)),
        }
        payload = await self._request(
            access_token=access_token,
            method="GET",
            url=f"{CALENDAR_API_BASE}/events",
            params=params,
        )
        return self._parse_event_items(payload.get("items", []))

    async def delete_event(
        self,
        *,
        access_token: str,
        event_id: str,
    ) -> CalendarEventSummary:
        event_payload = await self._request(
            access_token=access_token,
            method="GET",
            url=f"{CALENDAR_API_BASE}/events/{event_id}",
        )
        parsed = self._parse_event_items([event_payload])
        if not parsed:
            raise AppError("Calendar event not found.", code="calendar_event_not_found", status_code=404)

        has_attendees = bool(event_payload.get("attendees"))
        await self._request(
            access_token=access_token,
            method="DELETE",
            url=f"{CALENDAR_API_BASE}/events/{event_id}",
            params={"sendUpdates": "all" if has_attendees else "none"},
        )
        return parsed[0]

    def _parse_event_items(self, items: list[dict]) -> list[CalendarEventSummary]:
        events: list[CalendarEventSummary] = []
        for item in items:
            start = self._parse_event_time(item.get("start", {}))
            end = self._parse_event_time(item.get("end", {}))
            if start is None or end is None:
                continue
            attendees = [
                attendee.get("email", "")
                for attendee in item.get("attendees", [])
                if attendee.get("email")
            ]
            events.append(
                CalendarEventSummary(
                    id=item.get("id", ""),
                    title=item.get("summary") or "(untitled event)",
                    start=start,
                    end=end,
                    attendees=attendees,
                    location=item.get("location"),
                    description=item.get("description"),
                )
            )
        return events

    async def get_calendar_timezone(self, *, access_token: str, fallback: str = "UTC") -> str:
        try:
            payload = await self._request(
                access_token=access_token,
                method="GET",
                url=CALENDAR_SETTINGS_TIMEZONE,
            )
            timezone_name = payload.get("value")
            if timezone_name:
                return str(timezone_name)
        except AppError:
            pass
        return fallback

    async def create_event(
        self,
        *,
        access_token: str,
        title: str,
        start: datetime,
        end: datetime,
        time_zone: str,
        attendees: list[str] | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> CreatedCalendarEvent:
        if end <= start:
            raise AppError("Event end time must be after start time.", code="calendar_invalid_range")

        body: dict = {
            "summary": title,
            "start": self._format_event_time(start, time_zone=time_zone),
            "end": self._format_event_time(end, time_zone=time_zone),
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        normalized_attendees = [email.strip() for email in (attendees or []) if email.strip()]
        if normalized_attendees:
            body["attendees"] = [{"email": email} for email in normalized_attendees]

        payload = await self._request(
            access_token=access_token,
            method="POST",
            url=f"{CALENDAR_API_BASE}/events",
            params={"sendUpdates": "all" if normalized_attendees else "none"},
            json_body=body,
        )
        created_start = self._parse_event_time(payload.get("start", {}))
        created_end = self._parse_event_time(payload.get("end", {}))
        if created_start is None or created_end is None:
            raise AppError("Calendar event was created but response was incomplete.", code="calendar_api_error")

        return CreatedCalendarEvent(
            id=payload.get("id", ""),
            title=payload.get("summary") or title,
            start=created_start,
            end=created_end,
            html_link=payload.get("htmlLink"),
        )

    async def _request(
        self,
        *,
        access_token: str,
        method: str,
        url: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict:
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(method, url, headers=headers, params=params, json=json_body)
                if response.status_code == 401:
                    raise AppError(
                        "Calendar access denied. Reconnect Google Workspace with Calendar permissions.",
                        code="calendar_unauthorized",
                        status_code=401,
                    )
                if response.status_code == 429 and attempt < self.max_retries - 1:
                    continue
                if response.status_code == 404:
                    raise AppError(
                        "Calendar event not found.",
                        code="calendar_event_not_found",
                        status_code=404,
                    )
                if response.status_code == 403:
                    raise self._build_access_error(response)
                if response.status_code >= 400:
                    raise AppError(
                        "Unable to access Google Calendar.",
                        code="calendar_api_error",
                        status_code=502,
                        details=self._error_details(response),
                    )
                if response.status_code == 204 or not response.content:
                    return {}
                return response.json()
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.max_retries - 1:
                    break

        raise AppError(
            "Calendar request failed after retries.",
            code="calendar_request_failed",
            status_code=502,
            details={"error": str(last_error) if last_error else "unknown"},
        )

    @staticmethod
    def _parse_event_time(value: dict) -> datetime | None:
        if "dateTime" in value:
            return datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        if "date" in value:
            return datetime.fromisoformat(value["date"]).replace(tzinfo=timezone.utc)
        return None

    @staticmethod
    def _format_event_time(value: datetime, *, time_zone: str) -> dict[str, str]:
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
        return {"dateTime": format_local_datetime(value), "timeZone": time_zone}

    @staticmethod
    def parse_local_event_time(value: str) -> datetime:
        return parse_local_datetime(value)

    @staticmethod
    def _error_details(response: httpx.Response) -> dict:
        details: dict = {"status_code": response.status_code}
        try:
            payload = response.json()
            error = payload.get("error", {})
            if isinstance(error, dict):
                details["google_message"] = error.get("message")
                details["google_reason"] = error.get("errors", [{}])[0].get("reason")
            else:
                details["google_message"] = str(error)
        except ValueError:
            details["google_message"] = response.text[:500]
        return details

    def _build_access_error(self, response: httpx.Response) -> AppError:
        details = self._error_details(response)
        google_message = str(details.get("google_message", "")).lower()

        if "insufficient" in google_message and "scope" in google_message:
            message = (
                "Google Calendar permission was not granted. Log out, then sign in again "
                "and approve Calendar access on the Google consent screen."
            )
            code = "calendar_scope_missing"
        elif "not been used" in google_message or "disabled" in google_message:
            message = (
                "Google Calendar API is disabled for this Google Cloud project. Enable "
                "'Google Calendar API' in Google Cloud Console → APIs & Services → Library."
            )
            code = "calendar_api_disabled"
        else:
            message = (
                "Google Calendar access was denied. Enable the Calendar API in Google Cloud "
                "Console and reconnect your Google account with Calendar permissions."
            )
            code = "calendar_forbidden"

        return AppError(message, code=code, status_code=403, details=details)

    @staticmethod
    def format_events(events: list[CalendarEventSummary], *, timezone_name: str) -> str:
        if not events:
            return "No calendar events found for that period."
        lines: list[str] = []
        for index, event in enumerate(events, start=1):
            attendee_text = ", ".join(event.attendees) if event.attendees else "none"
            local_start = to_local_naive(event.start, timezone_name)
            local_end = to_local_naive(event.end, timezone_name)
            lines.append(
                f"{index}. [id={event.id}] {event.title}\n"
                f"   Start: {format_local_datetime(local_start)} ({timezone_name})\n"
                f"   End: {format_local_datetime(local_end)} ({timezone_name})\n"
                f"   Attendees: {attendee_text}"
            )
        return "\n\n".join(lines)
