from __future__ import annotations

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"

CALENDAR_READ_SCOPES = {
    CALENDAR_SCOPE,
    CALENDAR_READONLY_SCOPE,
    CALENDAR_EVENTS_SCOPE,
}

CALENDAR_WRITE_SCOPES = {
    CALENDAR_SCOPE,
    CALENDAR_EVENTS_SCOPE,
}


def parse_scope_list(scopes: str | list[str]) -> set[str]:
    if isinstance(scopes, str):
        return {scope.strip() for scope in scopes.split() if scope.strip()}
    return {scope.strip() for scope in scopes if scope.strip()}


def has_gmail_access(scopes: str | list[str]) -> bool:
    return GMAIL_READONLY_SCOPE in parse_scope_list(scopes)


def has_calendar_read_access(scopes: str | list[str]) -> bool:
    return bool(parse_scope_list(scopes) & CALENDAR_READ_SCOPES)


def has_calendar_write_access(scopes: str | list[str]) -> bool:
    return bool(parse_scope_list(scopes) & CALENDAR_WRITE_SCOPES)


def missing_calendar_scopes(scopes: str | list[str], *, require_write: bool = False) -> list[str]:
    granted = parse_scope_list(scopes)
    if require_write:
        if granted & CALENDAR_WRITE_SCOPES:
            return []
        return [CALENDAR_SCOPE]
    if granted & CALENDAR_READ_SCOPES:
        return []
    return [CALENDAR_SCOPE]
