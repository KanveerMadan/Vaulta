"""The account activity log (Settings → Activity). Names only in `detail`, never values."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.demo import is_demo
from app.models.activity import ActivityEvent

KINDS = ("sign_up", "sign_in", "export", "deleted", "telegram_linked", "telegram_unlinked", "address_regenerated",
         "settings_changed", "profile_changed", "reauth_failed", "password_reset_requested", "password_reset_completed",
         "password_changed", "method_linked", "method_unlinked", "signed_out_everywhere")
# Deleting the account deletes this log with it; the deletion itself is recorded in the server log
# (services/deletion.py) and confirmed to the user by email.
RECENT = 100


def record(db: Session, user, kind: str, detail: Optional[dict] = None) -> None:
    """Add an event to the session (the caller commits). The shared demo account keeps no log."""
    if kind not in KINDS:
        raise ValueError(f"unknown activity kind {kind}")
    if not is_demo(user):
        db.add(ActivityEvent(user_id=user.id, kind=kind, detail=detail))


def recent(db: Session, user) -> list[ActivityEvent]:
    return (db.query(ActivityEvent).filter(ActivityEvent.user_id == user.id)
            .order_by(ActivityEvent.created_at.desc()).limit(RECENT).all())
