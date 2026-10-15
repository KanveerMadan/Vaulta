"""Sending email through Resend (https://resend.com). Tests replace `send`."""

from __future__ import annotations

import httpx

from app.core.config import settings

RESEND_URL = "https://api.resend.com/emails"


class EmailError(Exception):
    pass


def configured() -> bool:
    return bool(settings.RESEND_API_KEY and settings.EMAIL_FROM)


def send(to: str, subject: str, html: str, text: str, headers: dict | None = None) -> str:
    """Send one email; returns Resend's message id."""
    if not configured():
        raise EmailError("Email isn't configured (RESEND_API_KEY, EMAIL_FROM).")
    try:
        res = httpx.post(RESEND_URL, timeout=15, headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                         json={"from": settings.EMAIL_FROM, "to": [to], "subject": subject, "html": html,
                               "text": text, "headers": headers or {}})
        res.raise_for_status()
        return res.json().get("id", "")
    except (httpx.HTTPError, ValueError) as e:
        raise EmailError(f"Resend: {e.__class__.__name__}") from e
