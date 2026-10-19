"""
Anomaly detection, run at the end of every detection pass.

Thresholds (listed in the Phase 3 report):
  duplicate charge   same merchant, same amount, ≤ 10 minutes apart, different references
                     (both must carry a real timestamp — date-only bank rows can't be told apart)
  unusual amount     > 3× the median of the user's earlier spends at that merchant (≥ 5 earlier)
  category spike     period spend > 1.5× the trailing 3-period average and ≥ ₹1,000 above it
  unreversed failed  debit marked failed/pending/declined, not reversed, older than 48 hours
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import median
from typing import Optional


from sqlalchemy.orm import Session

from app.core import clock
from app.models.anomaly import Anomaly
from app.models.transaction import Transaction, TransactionKind
from app.models.transaction_source import TransactionDirection
from app.models.user import User
from app.services import analytics
from app.services.keys import merchant_key
from app.services.recurring import add_months

DUPLICATE_WINDOW = timedelta(minutes=10)
UNUSUAL_MULTIPLE = Decimal(3)
UNUSUAL_MIN_HISTORY = 5
SPIKE_MULTIPLE = Decimal("1.5")
SPIKE_MIN_DIFFERENCE = Decimal("1000")
SPIKE_TRAILING_PERIODS = 3
FAILED_AFTER = timedelta(hours=48)
FAILED_PATTERN = re.compile(r"\bFAILED\b|\bPENDING\b|\bDECLINED\b", re.IGNORECASE)


def _label(t: Transaction) -> str:
    # normalized names only: anomaly details go into reports the LLM summarizes
    return t.merchant_clean or "Unknown merchant"


def _refs(t: Transaction) -> set[str]:
    refs = {r.utr for r in t.source_records if r.utr}
    return refs | {r.raw_row.get("reference") for r in t.source_records if isinstance(r.raw_row, dict) and r.raw_row.get("reference")}


def _timed(t: Transaction) -> bool:
    return any(r.raw_timestamp for r in t.source_records)


def _txn_info(t: Transaction) -> dict:
    return {"transaction_id": str(t.id), "date": t.transaction_date.date().isoformat(), "amount": str(analytics.money(t.amount))}


def duplicate_charges(txns: list[Transaction]) -> list[dict]:
    spends = sorted((t for t in txns if t.kind == TransactionKind.spend and _timed(t)), key=lambda t: t.transaction_date)
    found = []
    for i, a in enumerate(spends):
        for b in spends[i + 1:]:
            if b.transaction_date - a.transaction_date > DUPLICATE_WINDOW:
                break
            ra, rb = _refs(a), _refs(b)
            if b.amount == a.amount and merchant_key(a) == merchant_key(b) and ra and rb and not (ra & rb):
                found.append({"key": f"duplicate:{a.id}:{b.id}", "type": "duplicate_charge", "occurred_on": b.transaction_date.date(),
                              "details": {"merchant": _label(a), "amount": str(analytics.money(a.amount)),
                                          "transactions": [_txn_info(a), _txn_info(b)]}})
    return found


def unusual_amounts(txns: list[Transaction]) -> list[dict]:
    history: dict[str, list[Decimal]] = {}
    found = []
    for t in sorted((t for t in txns if t.kind == TransactionKind.spend and t.person_id is None), key=lambda t: t.transaction_date):
        key = merchant_key(t)
        earlier = history.setdefault(key, [])
        if len(earlier) >= UNUSUAL_MIN_HISTORY:
            typical = Decimal(median(earlier))
            if t.amount > typical * UNUSUAL_MULTIPLE:
                found.append({"key": f"unusual:{t.id}", "type": "unusual_amount", "occurred_on": t.transaction_date.date(),
                              "details": {"merchant": _label(t), "amount": str(analytics.money(t.amount)),
                                          "typical": str(analytics.money(typical)), "transactions": [_txn_info(t)]}})
        earlier.append(t.amount)
    return found


def category_spikes(db: Session, user_id: uuid.UUID, periods: list[tuple[date, date]]) -> list[dict]:
    """
    periods: oldest first; the last is the period checked, the ones before it
    the trailing window (at least SPIKE_TRAILING_PERIODS). Nothing is a spike
    unless every trailing period has some recorded transactions: a month with
    no records is missing data, not ₹0 of spending (a new user's first month,
    or a gap between imported statements).
    """
    if len(periods) < SPIKE_TRAILING_PERIODS + 1:
        return []
    *trailing, (start, end) = periods[-(SPIKE_TRAILING_PERIODS + 1):]
    for s, e in trailing:
        lo, hi = analytics.bounds(s, e)
        if db.query(Transaction.id).filter(Transaction.user_id == user_id, Transaction.transaction_date >= lo,
                                           Transaction.transaction_date <= hi).first() is None:
            return []
    current = {g["label"]: g["total"] for g in analytics.spend_summary(db, user_id, start, end)["groups"]}
    past = [{g["label"]: g["total"] for g in analytics.spend_summary(db, user_id, s, e)["groups"]} for s, e in trailing]
    found = []
    for category, total in sorted(current.items()):
        average = analytics.money(sum((p.get(category, analytics.ZERO) for p in past), analytics.ZERO) / len(past))
        if total > average * SPIKE_MULTIPLE and total - average >= SPIKE_MIN_DIFFERENCE:
            found.append({"key": f"spike:{category}:{start.isoformat()}:{end.isoformat()}", "type": "category_spike",
                          "occurred_on": start,
                          "details": {"category": category, "amount": str(total), "trailing_average": str(average),
                                      "start": start.isoformat(), "end": end.isoformat()}})
    return found


def monthly_spikes(db: Session, user_id: uuid.UUID, txns: list[Transaction], today: date) -> list[dict]:
    """Category spikes for every month that has a full trailing window, up to the current month to date."""
    if not txns:
        return []
    first = min(t.transaction_date.date() for t in txns).replace(day=1)
    found, month = [], add_months(first, SPIKE_TRAILING_PERIODS)
    while month <= today:
        periods = [analytics.month_bounds(add_months(month, -k)) for k in range(SPIKE_TRAILING_PERIODS, -1, -1)]
        found += category_spikes(db, user_id, periods)
        month = add_months(month, 1)
    return found


def unreversed_failed(txns: list[Transaction], now: datetime) -> list[dict]:
    return [
        {"key": f"failed:{t.id}", "type": "unreversed_failed_upi", "occurred_on": t.transaction_date.date(),
         "details": {"merchant": _label(t), "amount": str(analytics.money(t.amount)), "transactions": [_txn_info(t)]}}
        for t in txns
        if t.direction == TransactionDirection.debit and t.kind != TransactionKind.reversal
        and FAILED_PATTERN.search(t.merchant_raw or "") and now - t.transaction_date > FAILED_AFTER
    ]


def sync_anomalies(db: Session, user: User, txns: list[Transaction], today: Optional[date] = None) -> None:
    today = today or clock.today()
    now = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)
    detected = {a["key"]: a for a in duplicate_charges(txns) + unusual_amounts(txns)
                + monthly_spikes(db, user.id, txns, today) + unreversed_failed(txns, now)}
    existing = {a.key: a for a in db.query(Anomaly).filter(Anomaly.user_id == user.id)}
    for key, a in detected.items():
        row = existing.get(key) or Anomaly(user_id=user.id, key=key, status="open")
        row.type, row.occurred_on, row.details = a["type"], a["occurred_on"], a["details"]
        db.add(row)
    for key, row in existing.items():
        if key not in detected and row.status == "open":
            db.delete(row)   # no longer true (e.g. the failed debit got reversed)
