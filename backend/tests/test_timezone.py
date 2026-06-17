from datetime import date, datetime

from app.services.calendar import CalendarService
from app.services.timezone_utils import day_bounds, parse_local_datetime, to_local_naive
from app.schemas.workspace import CalendarEventSummary


def test_parse_local_datetime_strips_z_suffix() -> None:
    parsed = parse_local_datetime("2026-06-17T15:00:00Z")
    assert parsed == datetime(2026, 6, 17, 15, 0, 0)


def test_format_event_time_uses_local_timezone() -> None:
    payload = CalendarService._format_event_time(
        datetime(2026, 6, 17, 15, 0, 0),
        time_zone="Asia/Kolkata",
    )
    assert payload == {"dateTime": "2026-06-17T15:00:00", "timeZone": "Asia/Kolkata"}


def test_format_events_shows_local_time() -> None:
    events = [
        CalendarEventSummary(
            id="evt-1",
            title="Meeting",
            start=datetime(2026, 6, 17, 9, 30, tzinfo=datetime.now().astimezone().tzinfo),
            end=datetime(2026, 6, 17, 10, 30, tzinfo=datetime.now().astimezone().tzinfo),
            attendees=[],
            location=None,
            description=None,
        )
    ]
    # Use UTC start/end for predictable conversion
    from datetime import timezone

    events[0] = CalendarEventSummary(
        id="evt-1",
        title="Meeting",
        start=datetime(2026, 6, 17, 9, 30, tzinfo=timezone.utc),
        end=datetime(2026, 6, 17, 10, 30, tzinfo=timezone.utc),
        attendees=[],
        location=None,
        description=None,
    )
    text = CalendarService.format_events(events, timezone_name="Asia/Kolkata")
    assert "2026-06-17T15:00:00" in text


def test_day_bounds_for_local_date() -> None:
    start, end = day_bounds("Asia/Kolkata", date(2026, 6, 17))
    assert to_local_naive(start, "Asia/Kolkata").hour == 0
