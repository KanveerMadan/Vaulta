"""The current date and time in one place, so tests can pin them."""

from datetime import date, datetime, timezone


def today() -> date:
    return date.today()


def now() -> datetime:
    """Current instant, timezone-aware (UTC)."""
    return datetime.now(timezone.utc)
