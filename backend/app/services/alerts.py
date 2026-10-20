"""
Proactive alerts.

Evaluated at the end of every detection pass (so after every statement batch,
inbound alert email, manual/Telegram entry and edit) and, for date-based ones,
in the hourly internal run. Each alert is stored once: its key is type +
subject + period, and a key that exists is never alerted again.

Types and triggers (thresholds listed in the Phase 5 report):
  budget_threshold       a category (or the overall cap) reaches 80% / 100% of this month's limit; once each
  duplicate_charge       a duplicate_charge anomaly (services/anomalies.py)
  failed_upi_unreversed  an unreversed failed debit (anomaly, > 48 h old)
  unusual_amount         an unusual_amount anomaly (> 3× the merchant's median)
  price_change           a recurring series whose amount changed (> 5%)
  salary_received        income ≥ ₹10,000, or income from a source that also paid 25–35 days earlier
  renewal_tomorrow       a committed recurring series due tomorrow (user's local date; hourly run)
Transaction-based alerts only fire for things dated within RECENT_DAYS, so
importing months of history doesn't replay old news.

Channels: in-app always; Telegram when linked and enabled for the type, held
during quiet hours (default 22:00–08:00 local) and sent by the hourly run;
email by default only for duplicate_charge and failed_upi_unreversed.
Messages carry merchant labels and amounts only, never narrations.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core import clock
from app.core.demo import is_demo
from app.models.alert import Alert
from app.models.anomaly import Anomaly
from app.models.recurring import RecurringSeries
from app.models.transaction import Transaction, TransactionKind
from app.models.user import User
from app.services import analytics, email, telegram
from app.services.keys import merchant_key
from app.core.logs import user_ref

logger = logging.getLogger(__name__)

TYPES = ("budget_threshold", "duplicate_charge", "failed_upi_unreversed", "renewal_tomorrow", "price_change",
         "salary_received", "unusual_amount")
LABELS = {
    "budget_threshold": "Budget reaches 80% / 100%", "duplicate_charge": "Possible duplicate charge",
    "failed_upi_unreversed": "Failed payment not refunded", "renewal_tomorrow": "Bill or subscription due tomorrow",
    "price_change": "Subscription price change", "salary_received": "Salary or large income received",
    "unusual_amount": "Unusually large payment",
}
EMAIL_BY_DEFAULT = {"duplicate_charge", "failed_upi_unreversed"}
BUDGET_THRESHOLDS = (100, 80)          # highest first: jumping straight past 100% sends one alert, not two
RECENT_DAYS = 7
SALARY_MIN = Decimal("10000")
SALARY_REPEAT_DAYS = (25, 35)          # same income source this many days earlier → recurring income
EMAIL_RETRY_WINDOW = timedelta(days=1)
ANOMALY_TYPES = {"duplicate_charge": "duplicate_charge", "unreversed_failed_upi": "failed_upi_unreversed",
                 "unusual_amount": "unusual_amount"}


def rupees(v) -> str:
    from app.services.chat_tools import inr   # chat_tools imports detection, which imports this module
    return inr(v)


# ── Preferences and quiet hours ───────────────────────────────────────────────

def channels(user: User) -> dict[str, dict[str, bool]]:
    saved = user.alert_prefs or {}
    return {t: {"telegram": bool(saved.get(t, {}).get("telegram", True)),
                "email": bool(saved.get(t, {}).get("email", t in EMAIL_BY_DEFAULT))} for t in TYPES}


def in_quiet_hours(user: User, now: datetime) -> bool:
    hour = now.astimezone(clock.zone(user.timezone)).hour
    start, end = user.quiet_start, user.quiet_end
    if start == end:
        return False
    return start <= hour < end if start < end else (hour >= start or hour < end)


# ── Detection ─────────────────────────────────────────────────────────────────

def _budget_alerts(db: Session, user: User, today: date) -> list[tuple[str, str, str]]:
    status = analytics.budget_status(db, user.id, today)
    month = status["month"]
    month_name = today.strftime("%B")
    out = []
    for line in ([status["overall"]] if status["overall"] else []) + status["categories"]:
        if line["pct"] is None:
            continue
        name = "Your monthly budget" if line["category"] == "Overall" else f"{line['category']} budget"
        for threshold in BUDGET_THRESHOLDS:
            if line["pct"] >= threshold:
                used = "used up" if threshold == 100 else f"{threshold}% used"
                out.append(("budget_threshold", f"budget_threshold:{line['category']}:{month}:{threshold}",
                            f"{name} {used}: {rupees(line['spent'])} of {rupees(line['limit'])} in {month_name}."))
                break
    return out


def _anomaly_alerts(db: Session, user: User, since: date) -> list[tuple[str, str, str]]:
    out = []
    for a in db.query(Anomaly).filter(Anomaly.user_id == user.id, Anomaly.status == "open", Anomaly.occurred_on >= since):
        kind = ANOMALY_TYPES.get(a.type)
        if not kind:
            continue
        d = a.details
        text = {
            "duplicate_charge": f"Possible duplicate charge: {d['merchant']} {rupees(d['amount'])}, twice within 10 minutes.",
            "failed_upi_unreversed": f"A failed payment of {rupees(d['amount'])} to {d['merchant']} on {a.occurred_on:%d %b} hasn't been refunded yet.",
            "unusual_amount": f"Unusual amount: {rupees(d['amount'])} at {d['merchant']} (usually about {rupees(d.get('typical', 0))}).",
        }[kind]
        out.append((kind, f"{kind}:{a.key}", text))
    return out


def _price_alerts(db: Session, user: User, since: date) -> list[tuple[str, str, str]]:
    out = []
    for s in db.query(RecurringSeries).filter(RecurringSeries.user_id == user.id, RecurringSeries.previous_amount.isnot(None),
                                              RecurringSeries.last_date >= since):
        if s.user_status == "dismissed":
            continue
        name = s.user_name or s.display_name
        out.append(("price_change", f"price_change:{s.key}:{analytics.money(s.typical_amount)}",
                    f"{name} changed price: {rupees(s.previous_amount)} → {rupees(s.typical_amount)}."))
    return out


def _salary_alerts(txns: list[Transaction], since: date) -> list[tuple[str, str, str]]:
    incomes = [t for t in txns if t.kind == TransactionKind.income and not t.is_split]
    by_source: dict[str, list[date]] = {}
    for t in incomes:
        by_source.setdefault(merchant_key(t), []).append(t.transaction_date.date())
    out = []
    lo, hi = SALARY_REPEAT_DAYS
    for t in incomes:
        day = t.transaction_date.date()
        if day < since:
            continue
        repeats = any(lo <= (day - d).days <= hi for d in by_source[merchant_key(t)])
        if t.amount >= SALARY_MIN or repeats:
            source = f" from {t.merchant_clean}" if t.merchant_clean else ""
            out.append(("salary_received", f"salary_received:{t.id}", f"Income received: {rupees(t.amount)}{source}."))
    return out


def renewals_tomorrow(db: Session, user: User, local_today: date) -> list[tuple[str, str, str]]:
    tomorrow = local_today + timedelta(days=1)
    out = []
    for s in db.query(RecurringSeries).filter(RecurringSeries.user_id == user.id, RecurringSeries.next_expected == tomorrow,
                                              RecurringSeries.status.in_(analytics.COMMITTED_STATUSES)):
        if s.user_status == "dismissed":
            continue
        out.append(("renewal_tomorrow", f"renewal_tomorrow:{s.key}:{tomorrow.isoformat()}",
                    f"{s.user_name or s.display_name} is due tomorrow: {rupees(s.typical_amount)}."))
    return out


def _store(db: Session, user: User, found: list[tuple[str, str, str]]) -> list[Alert]:
    existing = {k for (k,) in db.query(Alert.key).filter(Alert.user_id == user.id)}
    new = []
    for kind, key, message in found:
        if key in existing:
            continue
        existing.add(key)
        alert = Alert(user_id=user.id, type=kind, key=key[:200], message=message[:500])
        db.add(alert)
        new.append(alert)
    db.flush()
    return new


def evaluate(db: Session, user: User, txns: list[Transaction], today: Optional[date] = None) -> list[Alert]:
    """Find and store new alerts after an ingest. Caller commits, then calls deliver_new()."""
    today = today or clock.today()
    since = today - timedelta(days=RECENT_DAYS)
    found = _budget_alerts(db, user, today) + _anomaly_alerts(db, user, since) + _price_alerts(db, user, since) \
        + _salary_alerts(txns, since)
    return _store(db, user, found)


# ── Delivery ──────────────────────────────────────────────────────────────────

def _deliverable(user: User) -> bool:
    return not is_demo(user)       # demo data never leaves the app


def _send_telegram(alert: Alert, user: User) -> None:
    try:
        telegram.send(user.telegram_chat_id, alert.message)
        alert.telegram_status = "sent"
    except telegram.TelegramError as e:
        alert.telegram_status = "queued"      # retried by the hourly run
        logger.warning(f"alerts: telegram failed user={user_ref(user.id)}: {e.__class__.__name__}")


def _send_email(alert: Alert, user: User, now: datetime) -> None:
    from app.core.config import settings
    link = f"{settings.APP_BASE_URL.rstrip('/')}/"
    text = f"{alert.message}\n\nOpen vaulta.in: {link}\n\nYou get this email because this alert type is on in your vaulta.in settings."
    from html import escape
    from app.services.report_email import button, shell
    html = shell("Alert", LABELS[alert.type],
                 f'<p style="margin:0;font-size:16px;line-height:1.6">{escape(alert.message)}</p>{button(link, "Open vaulta.in")}',
                 "You get this email because this alert type is on in your vaulta.in settings.")
    try:
        email.send(user.email, f"vaulta.in: {LABELS[alert.type]}", html, text)
        alert.email_sent_at = now
    except email.EmailError as e:
        logger.warning(f"alerts: email failed user={user_ref(user.id)}: {e.__class__.__name__}")


def deliver(db: Session, user: User, alerts: list[Alert], now: Optional[datetime] = None) -> None:
    """Send new alerts on the channels the user chose. Telegram waits out quiet hours."""
    if not alerts or not _deliverable(user):
        return
    now = now or clock.now()
    prefs, quiet = channels(user), in_quiet_hours(user, now)
    for alert in alerts:
        want = prefs[alert.type]
        if want["telegram"] and user.telegram_chat_id and telegram.configured():
            if quiet:
                alert.telegram_status = "queued"
            else:
                _send_telegram(alert, user)
        if want["email"] and user.email and email.configured():
            _send_email(alert, user, now)
    db.commit()


def run_hourly(db: Session, user: User, now: Optional[datetime] = None) -> dict:
    """Date-based alerts (renewal_tomorrow), then anything held for quiet hours or a failed send."""
    now = now or clock.now()
    local_today = now.astimezone(clock.zone(user.timezone)).date()
    new = _store(db, user, renewals_tomorrow(db, user, local_today))
    db.commit()
    deliver(db, user, new, now)
    sent = 0
    if _deliverable(user):
        prefs = channels(user)
        if user.telegram_chat_id and telegram.configured() and not in_quiet_hours(user, now):
            for alert in db.query(Alert).filter(Alert.user_id == user.id, Alert.telegram_status == "queued"):
                if prefs[alert.type]["telegram"]:
                    _send_telegram(alert, user)
                    sent += alert.telegram_status == "sent"
                else:
                    alert.telegram_status = None
        if user.email and email.configured():
            for alert in db.query(Alert).filter(Alert.user_id == user.id, Alert.email_sent_at.is_(None),
                                                Alert.created_at >= now - EMAIL_RETRY_WINDOW):
                if prefs[alert.type]["email"] and alert not in new:
                    _send_email(alert, user, now)
        db.commit()
    return {"new": len(new), "telegram_sent": sent}
