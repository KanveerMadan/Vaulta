"""The current date and time in one place, so tests can pin them."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Kolkata"


def today() -> date:
    return date.today()


def now() -> datetime:
    """Current instant, timezone-aware (UTC)."""
    return datetime.now(timezone.utc)


def zone(name: str | None) -> ZoneInfo:
    """A user's timezone; unknown or empty names fall back to India."""
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)
