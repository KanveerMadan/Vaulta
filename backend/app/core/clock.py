"""Today's date in one place, so tests can pin it (recurring status, loan ages, budget windows)."""

from datetime import date


def today() -> date:
    return date.today()
