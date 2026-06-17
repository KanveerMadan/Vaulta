"""
Gmail OAuth Routes — Phase 2

  GET  /api/gmail/auth      -> redirect to Google consent screen
  GET  /api/gmail/callback  -> exchange code, store encrypted tokens, trigger initial sync
  POST /api/gmail/sync      -> manual "Sync now" (rate-limited, see Section 0 rate limits)
  POST /api/gmail/disconnect -> revoke local tokens (does not revoke Google grant — user can do that at myaccount.google.com)

State parameter security:
  The `state` param passed to Google is the user's Firebase UID, signed with
  SECRET_KEY (HMAC) so the callback can verify it wasn't tampered with and
  know which user to attach tokens to — the callback request itself is
  unauthenticated (it's a redirect from Google, no Firebase token attached).
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.encryption import encrypt_token
from app.models.user import User
from app.services.gmail_oauth_service import (
    get_authorization_url,
    exchange_code_for_tokens,
    token_expiry_from_now,
    GmailOAuthError,
)
from app.services.gmail_sync_service import sync_gmail_for_user, GmailSyncError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gmail", tags=["gmail"])

# Frontend URL to redirect to after OAuth completes (success or failure)
FRONTEND_CONNECT_URL_SUFFIX = "/connect"


def _sign_state(firebase_uid: str) -> str:
    """HMAC-sign the firebase_uid so the callback can verify it wasn't tampered with."""
    sig = hmac.new(settings.SECRET_KEY.encode(), firebase_uid.encode(), hashlib.sha256).hexdigest()
    return f"{firebase_uid}.{sig}"


def _verify_state(state: str) -> str:
    """Verify and extract firebase_uid from a signed state string. Raises ValueError if invalid."""
    try:
        firebase_uid, sig = state.rsplit(".", 1)
    except ValueError:
        raise ValueError("Malformed state parameter")

    expected_sig = hmac.new(settings.SECRET_KEY.encode(), firebase_uid.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("State signature mismatch — possible tampering")

    return firebase_uid


@router.get("/auth")
def initiate_gmail_auth(current_user: User = Depends(get_current_user)):
    """
    Returns the Google OAuth consent URL. Frontend redirects the browser to this URL.
    """
    try:
        state = _sign_state(current_user.firebase_uid)
        auth_url = get_authorization_url(state=state)
    except RuntimeError as e:
        # settings.require() raises RuntimeError if GOOGLE_CLIENT_ID etc. are missing
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Gmail connection is not configured yet: {e}",
        )

    return {"auth_url": auth_url}


@router.get("/callback")
async def gmail_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Google redirects here after user consents (or denies).
    This endpoint is NOT behind get_current_user — Google's redirect carries
    no Firebase token. We identify the user via the signed `state` param.
    """
    frontend_base = settings.cors_origins()[0] if settings.cors_origins() else "/"
    redirect_base = f"{frontend_base}{FRONTEND_CONNECT_URL_SUFFIX}"

    if error:
        logger.info(f"Gmail OAuth denied by user: {error}")
        return RedirectResponse(url=f"{redirect_base}?gmail_error=denied")

    if not code or not state:
        return RedirectResponse(url=f"{redirect_base}?gmail_error=invalid_request")

    try:
        firebase_uid = _verify_state(state)
    except ValueError as e:
        logger.warning(f"Gmail OAuth callback state verification failed: {e}")
        return RedirectResponse(url=f"{redirect_base}?gmail_error=invalid_state")

    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()
    if not user:
        logger.error(f"Gmail OAuth callback: no user found for firebase_uid={firebase_uid}")
        return RedirectResponse(url=f"{redirect_base}?gmail_error=user_not_found")

    try:
        token_data = await exchange_code_for_tokens(code)
    except GmailOAuthError as e:
        logger.error(f"Gmail token exchange failed for user {user.id}: {e}")
        return RedirectResponse(url=f"{redirect_base}?gmail_error=token_exchange_failed")

    # Store encrypted tokens
    user.gmail_access_token = encrypt_token(token_data["access_token"])

    if "refresh_token" in token_data:
        user.gmail_refresh_token = encrypt_token(token_data["refresh_token"])
    elif not user.gmail_refresh_token:
        # No refresh token returned AND we don't have one stored — user must
        # revoke access at myaccount.google.com and reconnect to get prompt=consent again
        logger.error(f"No refresh_token available for user {user.id} and none stored previously.")
        return RedirectResponse(url=f"{redirect_base}?gmail_error=no_refresh_token")

    user.gmail_connected = True
    db.commit()

    # Trigger initial full sync asynchronously (Celery task)
    try:
        from app.workers.gmail_sync_worker import initial_sync_task
        initial_sync_task.delay(str(user.id))
    except Exception as e:
        # Celery/Redis not configured — fall back to inline sync so the feature
        # still works without background workers (degraded but functional)
        logger.warning(f"Celery dispatch failed ({e}), running initial sync inline.")
        try:
            await sync_gmail_for_user(db, user, full_sync=True)
        except GmailSyncError as sync_err:
            logger.error(f"Inline initial Gmail sync failed for user {user.id}: {sync_err}")

    return RedirectResponse(url=f"{redirect_base}?gmail_connected=true")


@router.post("/sync")
async def manual_gmail_sync(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manual "Sync now" button. Rate limiting (3/day per Section 0) should be
    applied via middleware/dependency — not yet wired here, tracked as a
    Phase 0 follow-up.
    """
    if not current_user.gmail_connected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail is not connected for this account.",
        )

    try:
        result = await sync_gmail_for_user(db, current_user, full_sync=False)
    except GmailSyncError as e:
        if str(e) == "RECONNECT_REQUIRED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Your Gmail connection has expired. Please reconnect.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Sync failed. Please try again in a few minutes.",
        )

    return result


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_gmail(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Disconnect Gmail — clears stored tokens and sets gmail_connected = False.
    Does NOT revoke the OAuth grant on Google's side; the user can do that
    at https://myaccount.google.com/permissions if they wish.
    """
    current_user.gmail_connected = False
    current_user.gmail_access_token = None
    current_user.gmail_refresh_token = None
    current_user.gmail_last_sync_at = None
    db.commit()