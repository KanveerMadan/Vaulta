"""
Error monitoring with Sentry (go-live stage 4): errors only, and scrubbed before anything leaves the server.

Off unless SENTRY_DSN is set. No tracing, profiling, session data or logs product; no default PII, no local variables,
no request bodies. Every event and breadcrumb goes through scrub_event / scrub_breadcrumb, which keep only what helps
find a bug (the exception type, the code's stack frames, the route) and remove:
  - request bodies, cookies, headers, query strings, the user, extras and other contexts;
  - from free text (exception values, messages, breadcrumbs): emails and UPI IDs, amounts, long numbers, and anything
    quoted, which is where narrations, merchant names and people's names end up in Python's error messages.
tests/test_monitoring.py sends a real error through the app with personal data in every place and checks none of it
reaches the transport.
"""

from __future__ import annotations

import os
import re
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from app.core.config import settings

_TEXT = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*"), "[email-or-upi]"),
    (re.compile(r"(?:₹|\bINR|\bRs\.?)\s*-?[\d,]+(?:\.\d+)?", re.I), "[amount]"),
    (re.compile(r"(?<![\w.])-?\d[\d,]*\.\d{1,2}(?!\d)"), "[amount]"),
    (re.compile(r"\d{4,}"), "[number]"),
    (re.compile(r"'[^']*'|\"[^\"]*\""), "'[text]'"),
]
_KEEP_CONTEXTS = {"runtime", "os", "trace"}


def scrub_text(text: Optional[str]) -> Optional[str]:
    if not isinstance(text, str):
        return text
    for pattern, replacement in _TEXT:
        text = pattern.sub(replacement, text)
    return text


def _path_only(url: Optional[str]) -> Optional[str]:
    """A URL without its query string or fragment (they can carry tokens and search terms)."""
    if not isinstance(url, str):
        return None
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def scrub_breadcrumb(crumb: dict, hint: Optional[dict] = None) -> dict:
    data = crumb.get("data") or {}
    kept = {"method": data.get("method"), "status_code": data.get("status_code"), "url": _path_only(data.get("url"))}
    return {**{k: crumb[k] for k in ("type", "category", "level", "timestamp") if k in crumb},
            "message": scrub_text(crumb.get("message")),
            "data": {k: v for k, v in kept.items() if v is not None}}


def scrub_event(event: dict, hint: Optional[dict] = None) -> dict:
    request = event.get("request") or {}
    event["request"] = {k: v for k, v in {"method": request.get("method"), "url": _path_only(request.get("url"))}.items() if v}
    for key in ("user", "extra", "modules"):
        event.pop(key, None)
    event["contexts"] = {k: v for k, v in (event.get("contexts") or {}).items() if k in _KEEP_CONTEXTS}
    for exc in (event.get("exception") or {}).get("values") or []:
        exc["value"] = scrub_text(exc.get("value"))
        for frame in (exc.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    if isinstance(event.get("logentry"), dict):
        event["logentry"] = {"message": scrub_text(event["logentry"].get("message"))}
    if "message" in event:
        event["message"] = scrub_text(event["message"])
    crumbs = event.get("breadcrumbs")
    values = crumbs.get("values") if isinstance(crumbs, dict) else crumbs
    if values:
        event["breadcrumbs"] = {"values": [scrub_breadcrumb(c) for c in values]}
    return event


def init(**extra) -> bool:
    """Start Sentry if SENTRY_DSN is set. `extra` is for tests (a recording transport)."""
    if not settings.SENTRY_DSN:
        return False
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=os.environ.get("RENDER_GIT_COMMIT") or None,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        enable_logs=False,
        before_send=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
        **extra,
    )
    return True
