from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def timezone_info(timezone_name: str | None) -> ZoneInfo | None:
    if not timezone_name:
        return None
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown timezone: {timezone_name}") from error


def select_timezone(preferred: object, fallback: str | None) -> str | None:
    """Use a stored IANA timezone when valid, otherwise use the validated fallback."""
    if preferred:
        preferred_name = str(preferred)
        try:
            timezone_info(preferred_name)
            return preferred_name
        except ValueError:
            pass
    timezone_info(fallback)
    return fallback


def calendar_date(value: str, timezone_name: str | None = None) -> date:
    """Resolve an ISO timestamp to its calendar date in the requested timezone."""
    if len(value) == 10:
        return date.fromisoformat(value)

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    target_timezone = timezone_info(timezone_name)
    if parsed.tzinfo is not None and target_timezone is not None:
        parsed = parsed.astimezone(target_timezone)
    return parsed.date()


def monday_sunday_week(value: date) -> tuple[date, date]:
    week_start = value - timedelta(days=value.weekday())
    return week_start, week_start + timedelta(days=6)
