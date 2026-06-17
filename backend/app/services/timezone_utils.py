from __future__ import annotations

from datetime import date as date_type, datetime, time
from zoneinfo import ZoneInfo


def parse_local_datetime(value: str) -> datetime:
    """Parse a local datetime string without converting timezones."""
    normalized = value.strip().replace("Z", "").replace("z", "")
    if "+" in normalized[10:]:
        normalized = normalized.split("+", maxsplit=1)[0]
    if normalized.count("-") > 2 and "T" in normalized:
        date_part, time_part = normalized.split("T", maxsplit=1)
        if "-" in time_part:
            time_part = time_part.rsplit("-", maxsplit=1)[0]
            normalized = f"{date_part}T{time_part}"
    return datetime.fromisoformat(normalized)


def now_in_timezone(timezone_name: str) -> datetime:
    return datetime.now(ZoneInfo(timezone_name))


def format_local_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def parse_local_date(value: str) -> date_type:
    return date_type.fromisoformat(value.strip()[:10])


def to_local_naive(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)


def day_bounds(timezone_name: str, day: date_type) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_name)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day, time.max, tzinfo=tz)
    return start, end
