"""
Firebase App Check: proof that a request comes from Vaulta's own web app in a real browser (reCAPTCHA v3),
not a script. Checked on the routes bots would abuse: demo sessions, account creation (the first sign-in),
password-reset requests, imports and chat. Header: X-Firebase-AppCheck.

  APP_CHECK_ENFORCE=false (default)  monitor: requests without a valid token are logged, not refused
  APP_CHECK_ENFORCE=true             refused with 401 {code: app_check_failed}
  APP_CHECK_DEBUG_TOKEN              outside production only: this fixed value is accepted as a token (local runs and
                                     browser tests, which can't run reCAPTCHA); production refuses to start with it set
Turning enforcement on needs the Firebase console steps in docs/go-live.md.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)
HEADER = "X-Firebase-AppCheck"
FAILED = "We couldn't confirm this request came from the Vaulta app. Reload the page and try again."


def _valid(token: str) -> bool:
    if not token:
        return False
    debug = settings.APP_CHECK_DEBUG_TOKEN
    if debug and settings.ENVIRONMENT != "production":
        return hmac.compare_digest(token.encode(), debug.encode())
    try:
        from firebase_admin import app_check
        app_check.verify_token(token)
        return True
    except Exception as e:
        logger.info(f"app check: token rejected ({e.__class__.__name__})")
        return False


def check(request: Request) -> None:
    """Refuse (when enforcing) or log a request without a valid App Check token."""
    from app.core.auth import CodedError
    if _valid(request.headers.get(HEADER, "")):
        return
    route = getattr(request.scope.get("route"), "path", request.url.path)
    if settings.APP_CHECK_ENFORCE:
        raise CodedError(status.HTTP_401_UNAUTHORIZED, "app_check_failed", FAILED)
    logger.info(f"app check: missing or invalid token on {route} (monitor mode)")


def require_app_check(request: Request) -> None:
    """FastAPI dependency form of check()."""
    check(request)
