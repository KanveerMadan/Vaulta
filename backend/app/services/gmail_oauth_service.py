"""
Gmail OAuth Service — Phase 2

Handles the OAuth2 flow for Gmail read-only access, scoped to transaction-relevant
senders only. Tokens are Fernet-encrypted before storage (app.core.encryption).

Scope design:
  - We request `gmail.readonly` (the narrowest read scope Google offers — there's
    no per-sender OAuth scope). The NARROWING happens at query-time: every Gmail
    API call filters with `q=` to only fetch emails from known transaction senders
    (Swiggy, Zomato, Amazon, Flipkart, IRCTC, BookMyShow, banks, etc).
  - We NEVER call messages.list without a sender filter — this is enforced in
    gmail_sync_service, not here, but documented here because it's the privacy
    commitment this OAuth grant depends on.

Flow:
  1. GET /api/gmail/auth -> get_authorization_url() -> redirect user to Google
  2. Google redirects back to /api/gmail/callback with `code`
  3. exchange_code_for_tokens(code) -> {access_token, refresh_token, expires_in}
  4. Store tokens encrypted on User model
  5. gmail_sync_service uses refresh_access_token() when access_token expires
"""


from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

GOOGLE_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Narrowest read scope available. Per-sender filtering happens at query time.
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "email",
]


class GmailOAuthError(Exception):
    """Raised on any OAuth flow failure — surfaced as 502/400 by route handlers."""
    pass


def get_authorization_url(state: str) -> str:
    """
    Build the Google OAuth consent URL.

    `state` should be a signed/opaque token tying this request to the
    authenticated user (e.g. their Firebase UID or a short-lived JWT) —
    the callback uses it to know which user to attach tokens to.
    """
    settings.require("GOOGLE_CLIENT_ID", "GOOGLE_REDIRECT_URI")

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",  # Required to receive a refresh_token
        "prompt": "consent",       # Force consent screen so refresh_token is always issued
        "state": state,
    }
    return f"{GOOGLE_AUTH_BASE}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """
    Exchange an authorization code for access_token + refresh_token.

    Returns:
        {
          "access_token": str,
          "refresh_token": str,  # Only present on first consent
          "expires_in": int,     # Seconds until access_token expires
          "token_type": "Bearer",
          "scope": str,
        }

    Raises:
        GmailOAuthError on any failure.
    """
    settings.require("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
        except httpx.RequestError as e:
            raise GmailOAuthError(f"Failed to reach Google's token endpoint: {e}") from e

    if resp.status_code != 200:
        logger.error(f"Gmail token exchange failed: {resp.status_code} {resp.text}")
        raise GmailOAuthError(
            "Google rejected the authorization code. The user may need to retry connecting Gmail."
        )

    data = resp.json()
    if "refresh_token" not in data:
        # Happens if the user previously granted consent without `prompt=consent`.
        # The caller should handle this by checking if the user already has a
        # stored refresh_token before treating this as fatal.
        logger.warning("Gmail token exchange did not return a refresh_token.")

    return data


async def refresh_access_token(refresh_token: str) -> dict:
    """
    Use a stored refresh_token to obtain a new access_token.

    Returns:
        {"access_token": str, "expires_in": int, "token_type": "Bearer", "scope": str}

    Raises:
        GmailOAuthError — if the refresh token is invalid/revoked, the user
        must reconnect Gmail (caller should set user.gmail_connected = False).
    """
    settings.require("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                },
            )
        except httpx.RequestError as e:
            raise GmailOAuthError(f"Failed to reach Google's token endpoint: {e}") from e

    if resp.status_code == 400:
        # invalid_grant — refresh token revoked or expired
        logger.warning("Gmail refresh_token invalid/revoked — user must reconnect.")
        raise GmailOAuthError("REFRESH_TOKEN_INVALID")

    if resp.status_code != 200:
        logger.error(f"Gmail token refresh failed: {resp.status_code} {resp.text}")
        raise GmailOAuthError("Failed to refresh Gmail access token.")

    return resp.json()


def token_expiry_from_now(expires_in: int) -> datetime:
    """Convert an `expires_in` (seconds) into an absolute UTC datetime."""
    return datetime.now(timezone.utc) + timedelta(seconds=expires_in)