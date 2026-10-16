"""Account-level actions on the Firebase login (Admin SDK): signing out everywhere."""

from __future__ import annotations

from datetime import datetime, timezone

from firebase_admin import auth as firebase_auth
from sqlalchemy.orm import Session

from app.services import activity


def sign_out_everywhere(db: Session, user, reason: str = "requested") -> None:
    """
    Revoke every refresh token (Firebase) and remember when, so ID tokens issued before now are refused on every
    request (app/core/auth.py issued_before_revocation). Telegram links and demo sessions don't use Firebase tokens
    and are unaffected. The caller commits.
    """
    firebase_auth.revoke_refresh_tokens(user.firebase_uid)
    valid_after_ms = firebase_auth.get_user(user.firebase_uid).tokens_valid_after_timestamp
    user.tokens_revoked_at = datetime.fromtimestamp(valid_after_ms / 1000, tz=timezone.utc)
    activity.record(db, user, "signed_out_everywhere", {"reason": reason})
