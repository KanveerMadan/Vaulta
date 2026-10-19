"""Account-level actions on the Firebase login (Admin SDK): signing out everywhere, passwords, password resets."""

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


# ── Passwords ─────────────────────────────────────────────────────────────────

MIN_PASSWORD, MAX_PASSWORD = 10, 128


class PasswordRejected(ValueError):
    pass


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise PasswordRejected(f"Use at least {MIN_PASSWORD} characters.")
    if len(password) > MAX_PASSWORD:
        raise PasswordRejected(f"Use at most {MAX_PASSWORD} characters.")
    if not password.strip():
        raise PasswordRejected("The password can't be only spaces.")


def set_password(db: Session, user, password: str) -> str:
    """
    Change the password, or add one to a Google-only account. Every other session is signed out (the caller's own
    browser signs in again with the new password). Returns "password_changed" or "method_linked". Caller commits.
    """
    check_password(password)
    had_password = "password" in providers(user)
    firebase_auth.update_user(user.firebase_uid, password=password)
    kind = "password_changed" if had_password else "method_linked"
    activity.record(db, user, kind, None if had_password else {"method": "password"})
    sign_out_everywhere(db, user, reason=kind)
    return kind


def providers(user) -> list[str]:
    return [p.provider_id for p in firebase_auth.get_user(user.firebase_uid).provider_data]


# ── Password reset (the email itself is sent by Firebase from the browser) ────

def note_reset_requested(db: Session, email: str) -> None:
    """Remember a reset request for this address's account, if there is one. Says nothing either way."""
    from app.core.scope import find_user, unbind
    user = find_user(db, "email", email.strip())
    if user is None:
        return
    user.password_reset_requested_at = datetime.now(timezone.utc)
    activity.record(db, user, "password_reset_requested")
    db.commit()
    unbind(db)


def note_reset_completed(db: Session, user) -> None:
    """
    At a new sign-in after a reset was requested: Firebase revokes every session when a password is reset, so a
    revocation after the request means the reset was completed. Log it, and refuse the old sessions here too.
    """
    requested = user.password_reset_requested_at
    if requested is None:
        return
    valid_after_ms = firebase_auth.get_user(user.firebase_uid).tokens_valid_after_timestamp or 0
    if valid_after_ms // 1000 >= int(requested.timestamp()):     # Firebase keeps whole seconds
        user.tokens_revoked_at = datetime.fromtimestamp(valid_after_ms / 1000, tz=timezone.utc)
        activity.record(db, user, "password_reset_completed")
    user.password_reset_requested_at = None


# ── Sign-in methods (Google, password) on the one Firebase account ────────────

METHODS = ("password", "google.com")


class LastMethod(ValueError):
    pass


def unlink_method(db: Session, user, provider: str) -> None:
    """Remove a sign-in method; never the last one. Signs out every session. Caller commits."""
    current = providers(user)
    if provider not in current:
        raise KeyError(provider)
    if len(current) <= 1:
        raise LastMethod("That's the only way to sign in to this account. Add another method first.")
    firebase_auth.update_user(user.firebase_uid, providers_to_delete=[provider])
    activity.record(db, user, "method_unlinked", {"method": provider})
    sign_out_everywhere(db, user, reason="method_unlinked")


def note_linked(db: Session, user, provider: str) -> bool:
    """The web app linked a method in Firebase (Google popup): log it once Firebase confirms it's there."""
    if provider not in providers(user):
        return False
    activity.record(db, user, "method_linked", {"method": provider})
    return True
