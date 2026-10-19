"""
reCAPTCHA v3, verified by the API (Google's siteverify): evidence that a request comes from a person using Vaulta's
web app, not a script. Firebase App Check isn't used: its reCAPTCHA v3 provider is deprecated, and the replacement
needs billing. Checked where bots would do harm: demo sessions, account creation (the first sign-in), password-reset
requests, imports and chat. The browser sends a fresh token per request in X-Recaptcha-Token (frontend/src/lib/recaptcha.js).

A token is good when Google says it's valid, for this action, from Vaulta's own host. Then its score (0.0 bot ..
1.0 person) decides:
  score >= RECAPTCHA_MIN_SCORE (0.5)  normal
  lower                               never refused for the score alone: the request goes through, but under a
                                      much tighter rate limit (LOW_SCORE_LIMIT per hour per IP and action), and
                                      everything that writes data already needs a verified email (core/auth.py)
Modes:
  RECAPTCHA_ENFORCE=false (default)   monitor: every outcome is logged, nothing is refused or slowed
  RECAPTCHA_ENFORCE=true              no token, or an invalid one: 401 {code: recaptcha_failed}; low score: slowed
If Google can't be reached, the request is let through and logged: an outage there must not take Vaulta down.
RECAPTCHA_DEBUG_TOKEN is accepted as a valid, high-score token outside production only (local runs and browser
tests, which can't run reCAPTCHA); production refuses to start with it set.
"""

from __future__ import annotations

import hmac
import logging
from typing import Optional
from urllib.parse import urlsplit

import httpx
from fastapi import Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)
HEADER = "X-Recaptcha-Token"
SITEVERIFY = "https://www.google.com/recaptcha/api/siteverify"
LOW_SCORE_LIMIT, LOW_SCORE_WINDOW = 5, 3600
FAILED = "We couldn't confirm this request came from the Vaulta app. Reload the page and try again."
SLOWED = "We're seeing unusual activity from your connection. Try again in a little while."


def _allowed_hosts() -> set[str]:
    host = urlsplit(settings.APP_BASE_URL).hostname or ""
    return {host, f"www.{host}"}


def verify(token: str, action: str, ip: Optional[str] = None) -> tuple[str, Optional[float]]:
    """('ok' | 'low' | 'invalid' | 'missing' | 'unavailable', score)."""
    if not token:
        return "missing", None
    debug = settings.RECAPTCHA_DEBUG_TOKEN
    if debug and settings.ENVIRONMENT != "production" and hmac.compare_digest(token.encode(), debug.encode()):
        return "ok", 1.0
    if not settings.RECAPTCHA_SECRET_KEY:
        return "unavailable", None
    try:
        res = httpx.post(SITEVERIFY, data={"secret": settings.RECAPTCHA_SECRET_KEY, "response": token,
                                           **({"remoteip": ip} if ip else {})}, timeout=5.0)
        res.raise_for_status()
        body = res.json()
    except Exception as e:
        logger.warning(f"recaptcha: siteverify unreachable ({e.__class__.__name__})")
        return "unavailable", None
    if not body.get("success") or body.get("action") != action:
        return "invalid", None
    if settings.ENVIRONMENT == "production" and body.get("hostname") not in _allowed_hosts():
        return "invalid", None
    score = float(body.get("score", 0.0))
    return ("ok" if score >= settings.RECAPTCHA_MIN_SCORE else "low"), score


def check(request: Request, action: str) -> None:
    """Refuse (enforcing, bad token), slow down (enforcing, low score) or just log one request."""
    from app.core import ratelimit
    from app.core.auth import CodedError
    ip = ratelimit.client_ip(request)
    outcome, score = verify(request.headers.get(HEADER, ""), action, ip)
    if outcome == "ok":
        return
    shown = f"{score:.1f}" if score is not None else "-"
    if not settings.RECAPTCHA_ENFORCE:
        logger.info(f"recaptcha: {outcome} (score {shown}) on {action} (monitor mode)")
        return
    logger.info(f"recaptcha: {outcome} (score {shown}) on {action}")
    if outcome in ("missing", "invalid"):
        raise CodedError(status.HTTP_401_UNAUTHORIZED, "recaptcha_failed", FAILED)
    if outcome == "low":
        ratelimit.check(f"recaptcha-low-{action}", ip, LOW_SCORE_LIMIT, LOW_SCORE_WINDOW, SLOWED)
    # 'unavailable': let it through (logged above)


def require(action: str):
    """FastAPI dependency: Depends(recaptcha.require("demo"))."""
    def dependency(request: Request) -> None:
        check(request, action)
    return dependency
