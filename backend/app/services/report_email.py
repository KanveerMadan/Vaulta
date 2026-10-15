"""
Report emails: HTML with a plain-text fallback, a link to the full report in
the app, and an unsubscribe link for that report type (one-click, RFC 8058).
"""

from __future__ import annotations

import hashlib
import hmac
from html import escape
from typing import Optional

from app.core.config import settings
from app.models.report import Report
from app.models.user import User
from app.services.chat_tools import inr

TYPE_NAMES = {"weekly": "weekly", "monthly": "monthly", "annual": "annual"}


# ── Unsubscribe tokens: user id + report type, signed with SECRET_KEY ─────────

def unsubscribe_token(user: User, period_type: str) -> str:
    payload = f"{user.id}:{period_type}"
    sig = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}:{sig}"


def read_unsubscribe_token(token: str) -> Optional[tuple[str, str]]:
    """(user id, report type) if the token is genuine, else None."""
    try:
        user_id, period_type, sig = token.split(":")
    except ValueError:
        return None
    expected = hmac.new(settings.SECRET_KEY.encode(), f"{user_id}:{period_type}".encode(), hashlib.sha256).hexdigest()[:32]
    if period_type not in TYPE_NAMES or not hmac.compare_digest(sig, expected):
        return None
    return user_id, period_type


def unsubscribe_url(user: User, period_type: str) -> str:
    return f"{settings.API_BASE_URL.rstrip('/')}/unsubscribe?token={unsubscribe_token(user, period_type)}"


def report_url(report: Report) -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/reports/{report.id}"


# ── Rendering ─────────────────────────────────────────────────────────────────

def _rows(pairs: list[tuple[str, str]]) -> str:
    return "".join(
        f'<tr><td style="padding:4px 0;color:#4A6B50">{escape(k)}</td>'
        f'<td style="padding:4px 0;text-align:right;font-family:monospace">{escape(v)}</td></tr>' for k, v in pairs)


def render(report: Report, user: User) -> tuple[str, str, str, dict]:
    """(subject, html, text, headers)."""
    d = report.json
    t, label = d["totals"], d["period"]["label"]
    subject = f"Your {TYPE_NAMES[report.period_type]} Vaulta report: {label}"
    totals = [("Spent", inr(t["spend"])), ("Income", inr(t["income"])), ("Saved", inr(t["saved"]))]
    if t["savings_rate_pct"] is not None:
        totals.append(("Savings rate", f"{t['savings_rate_pct']}%"))
    top = [(c["name"], inr(c["amount"])) for c in d["top_categories"]]
    wrapped = []
    if report.period_type == "annual" and d.get("wrapped"):
        w = d["wrapped"]
        if w.get("top_merchant_by_spend"):
            wrapped.append(("Biggest spend", f"{w['top_merchant_by_spend']['name']} {inr(w['top_merchant_by_spend']['amount'])}"))
        if w.get("most_expensive_month"):
            wrapped.append(("Most expensive month", f"{w['most_expensive_month']['month']} {inr(w['most_expensive_month']['amount'])}"))
        wrapped.append(("Subscriptions", inr(w["subscriptions_total"])))
        wrapped.append(("Transactions", str(w["transaction_count"])))
    link, unsub = report_url(report), unsubscribe_url(user, report.period_type)
    narrative_html = "<br>".join(escape(line) for line in report.narrative.splitlines())

    section = lambda title, pairs: (f'<h3 style="font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#8FAF98;margin:20px 0 6px">{escape(title)}</h3>'
                                    f'<table style="width:100%;border-collapse:collapse;font-size:14px">{_rows(pairs)}</table>') if pairs else ""
    html = f"""<!doctype html><html><body style="margin:0;background:#F2F7F3;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#1A2E1E">
<div style="max-width:560px;margin:0 auto;padding:24px 16px">
<p style="font-size:13px;color:#7A9E80;margin:0">Vaulta · {escape(TYPE_NAMES[report.period_type])} report</p>
<h1 style="font-size:22px;font-weight:600;margin:4px 0 16px">{escape(label)}</h1>
<div style="background:#fff;border:1px solid #D4E4D7;border-radius:12px;padding:16px 18px">
<p style="font-size:14px;line-height:1.6;margin:0">{narrative_html}</p>
{section("Totals", totals)}{section("Top categories", top)}{section("Money Wrapped", wrapped)}
<p style="margin:20px 0 0"><a href="{escape(link)}" style="background:#2D6A4F;color:#F2F7F3;text-decoration:none;padding:10px 16px;border-radius:8px;font-size:14px;display:inline-block">View the full report</a></p>
</div>
<p style="font-size:12px;color:#8FAF98;margin-top:16px">You get this because {escape(TYPE_NAMES[report.period_type])} reports are on in your Vaulta settings.
<a href="{escape(unsub)}" style="color:#8FAF98">Stop {escape(TYPE_NAMES[report.period_type])} emails</a>.</p>
</div></body></html>"""
    text = "\n".join(
        [f"Vaulta {TYPE_NAMES[report.period_type]} report: {label}", "", report.narrative, ""]
        + [f"{k}: {v}" for k, v in totals]
        + ([""] + ["Top categories:"] + [f"  {k}: {v}" for k, v in top] if top else [])
        + ([""] + ["Money Wrapped:"] + [f"  {k}: {v}" for k, v in wrapped] if wrapped else [])
        + ["", f"Full report: {link}", f"Stop {TYPE_NAMES[report.period_type]} emails: {unsub}"])
    headers = {"List-Unsubscribe": f"<{unsub}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    return subject, html, text, headers
