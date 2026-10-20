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

# Vaulta's "Ledger" identity in email-client-safe HTML: tables, inline styles, system fonts.
INK, MUTED, LINE, CANVAS, ACCENT = "#101511", "#56615A", "#D9DFDA", "#F4F6F3", "#17643F"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _rows(pairs: list[tuple[str, str]]) -> str:
    return "".join(
        f'<tr><td style="padding:10px 0;border-top:1px solid {LINE};color:{MUTED};font-size:14px">{escape(k)}</td>'
        f'<td style="padding:10px 0;border-top:1px solid {LINE};text-align:right;font-size:15px;font-weight:600;color:{INK};'
        f'font-variant-numeric:tabular-nums">{escape(v)}</td></tr>' for k, v in pairs)


def shell(eyebrow: str, heading: str, body_html: str, footer_html: str) -> str:
    """The frame every vaulta.in email shares: wordmark, heading, white panel, quiet footer."""
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>{escape(heading)}</title></head>
<body style="margin:0;padding:0;background:{CANVAS};font-family:{FONT};color:{INK}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CANVAS}"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px">
<tr><td style="padding:0 4px 20px"><span style="font-size:20px;font-weight:700;letter-spacing:-0.3px;color:{INK}"><span style="border-bottom:2px solid {ACCENT}">v</span>aulta<span style="color:{ACCENT}">.in</span></span></td></tr>
<tr><td style="padding:0 4px"><p style="margin:0;font-size:13px;color:{MUTED}">{escape(eyebrow)}</p>
<h1 style="margin:4px 0 18px;font-size:30px;line-height:1.1;font-weight:700;letter-spacing:-0.6px;color:{INK}">{escape(heading)}</h1></td></tr>
<tr><td style="background:#FFFFFF;border:1px solid {LINE};border-radius:12px;padding:22px 22px 24px">{body_html}</td></tr>
<tr><td style="padding:18px 4px 0;font-size:12px;line-height:1.6;color:{MUTED}">{footer_html}</td></tr>
</table></td></tr></table></body></html>"""


def button(href: str, label: str) -> str:
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:22px"><tr><td style="background:{ACCENT};border-radius:8px">'
            f'<a href="{escape(href)}" style="display:inline-block;padding:12px 18px;color:#FFFFFF;text-decoration:none;font-weight:600;font-size:14px">{escape(label)}</a>'
            f'</td></tr></table>')


GOAL_STATUS = {"done": "reached", "on_track": "on track", "behind": "behind", "not_started": "not started"}


def render(report: Report, user: User) -> tuple[str, str, str, dict]:
    """(subject, html, text, headers)."""
    d = report.json
    t, label = d["totals"], d["period"]["label"]
    subject = f"Your {TYPE_NAMES[report.period_type]} vaulta.in report: {label}"
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
    goals = [(g["name"], f"{inr(g['saved'])} of {inr(g['target_amount'])} · {GOAL_STATUS.get(g['status'], g['status'])}")
             for g in d.get("goals") or []]
    link, unsub = report_url(report), unsubscribe_url(user, report.period_type)
    narrative_html = "<br>".join(escape(line) for line in report.narrative.splitlines())

    section = lambda title, pairs: (f'<p style="margin:22px 0 4px;font-size:13px;font-weight:600;color:{MUTED}">{escape(title)}</p>'
                                    f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{_rows(pairs)}</table>') if pairs else ""
    body = (f'<p style="margin:0;font-size:16px;line-height:1.6;color:{INK}">{narrative_html}</p>'
            f'{section("Totals", totals)}{section("Top categories", top)}{section("Goals", goals)}{section("Money Wrapped", wrapped)}'
            f'{button(link, "View the full report")}')
    footer = (f'You get this because {escape(TYPE_NAMES[report.period_type])} reports are on in your vaulta.in settings. '
              f'<a href="{escape(unsub)}" style="color:{MUTED}">Stop {escape(TYPE_NAMES[report.period_type])} emails</a>.')
    html = shell(f"Your {TYPE_NAMES[report.period_type]} report", label, body, footer)
    text = "\n".join(
        [f"vaulta.in {TYPE_NAMES[report.period_type]} report: {label}", "", report.narrative, ""]
        + [f"{k}: {v}" for k, v in totals]
        + ([""] + ["Top categories:"] + [f"  {k}: {v}" for k, v in top] if top else [])
        + ([""] + ["Goals:"] + [f"  {k}: {v}" for k, v in goals] if goals else [])
        + ([""] + ["Money Wrapped:"] + [f"  {k}: {v}" for k, v in wrapped] if wrapped else [])
        + ["", f"Full report: {link}", f"Stop {TYPE_NAMES[report.period_type]} emails: {unsub}"])
    headers = {"List-Unsubscribe": f"<{unsub}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    return subject, html, text, headers
