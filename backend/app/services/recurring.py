"""
Recurring payment detection. Runs at the end of every detection pass.

Spend debits are grouped by merchant (or by person for P2P). Within a group
the most recent run of payments at a steady cadence is a series when:
  - consecutive gaps fit the cadence (monthly 27–34 days, weekly 6–8,
    yearly 355–375; i.e. ±3 days monthly, ±1 weekly, ±10 yearly)
  - amounts are within ±15% of their median, allowing ONE price change
    point (amounts before and after it each within ±15%)
  - at least 3 payments (2 for yearly)
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Optional

from sqlalchemy.orm import Session

from app.models.recurring import RecurringSeries
from app.models.transaction import Transaction, TransactionKind
from app.models.transaction_source import TransactionDirection
from app.models.user import User
from app.services.keys import merchant_key, person_identity, person_key

# ── Tunable thresholds (listed in the Phase 2 report) ─────────────────────────
CADENCES = {
    # name: (min gap days, max gap days, nominal days, min occurrences, due tolerance days)
    "weekly": (6, 8, 7, 3, 1),
    "monthly": (27, 34, 30, 3, 3),
    "yearly": (355, 375, 365, 2, 10),
}
AMOUNT_TOLERANCE = Decimal("0.15")
PRICE_CHANGE_THRESHOLD = Decimal("0.05")
CANCELLED_AFTER = Decimal("1.5")       # × cadence with no payment
RENT_MIN_AMOUNT = Decimal("5000")      # monthly P2P at least this → rent guess

_SUBSCRIPTION_CATEGORIES = {"Entertainment", "Software & Cloud", "Education"}
_BILL_CATEGORIES = {"Utilities", "Insurance", "Taxes & Government"}
_EMI = re.compile(r"\bEMI\b|\bLOAN\b|BAJAJ\s*FIN|HOME\s*CREDIT", re.IGNORECASE)
_SIP = re.compile(r"\bSIP\b|MUTUAL\s*FUND|\bMF\b|ZERODHA|GROWW|COIN\b", re.IGNORECASE)


@dataclass
class Detected:
    key: str
    display_name: str
    cadence: str
    typical_amount: Decimal
    last_amount: Decimal
    last_date: date
    next_expected: date
    occurrences: int
    status: str
    type_guess: str
    previous_amount: Optional[Decimal]
    category: Optional[str]
    established_on: date


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def next_date(d: date, cadence: str) -> date:
    if cadence == "weekly":
        return d + timedelta(days=7)
    if cadence == "monthly":
        return add_months(d, 1)
    return add_months(d, 12)


def _within(amounts: list[Decimal]) -> bool:
    m = Decimal(median(amounts))
    return all(abs(a - m) <= m * AMOUNT_TOLERANCE for a in amounts)


def _amount_profile(amounts: list[Decimal]) -> Optional[tuple[Decimal, Optional[Decimal]]]:
    """(typical, previous-if-price-changed) or None if amounts aren't steady."""
    if _within(amounts):
        before = amounts[:-1]
        prev = Decimal(median(before)) if before else None
        latest = amounts[-1]
        if prev and abs(latest - prev) > prev * PRICE_CHANGE_THRESHOLD:
            return latest, prev.quantize(Decimal("0.01"))
        return Decimal(median(amounts)).quantize(Decimal("0.01")), None
    # One price-change point: of the splits where both sides are steady, the
    # one whose sides are tightest (499, 499 | 649 rather than 499 | 499, 649)
    def spread(seg: list[Decimal]) -> Decimal:
        m = Decimal(median(seg))
        return sum((abs(a - m) for a in seg), Decimal("0"))

    splits = [k for k in range(1, len(amounts)) if _within(amounts[:k]) and _within(amounts[k:])]
    if not splits:
        return None
    k = min(splits, key=lambda k: spread(amounts[:k]) + spread(amounts[k:]))
    old, new = Decimal(median(amounts[:k])), Decimal(median(amounts[k:]))
    if abs(new - old) > old * PRICE_CHANGE_THRESHOLD:
        return new.quantize(Decimal("0.01")), old.quantize(Decimal("0.01"))
    return new.quantize(Decimal("0.01")), None


def _trailing_run(txns: list[Transaction], cadence: str) -> list[Transaction]:
    lo, hi, *_ = CADENCES[cadence]
    run = [txns[-1]]
    for t in reversed(txns[:-1]):
        gap = (run[0].transaction_date.date() - t.transaction_date.date()).days
        if gap == 0:
            continue  # same-day duplicate payment; not part of the cadence
        if not lo <= gap <= hi:
            break
        run.insert(0, t)
    return run


def _type_guess(txns: list[Transaction], cadence: str, is_person: bool, typical: Decimal) -> str:
    category = txns[-1].category
    text = " ".join(t.merchant_raw or "" for t in txns[-3:])
    if category == "Rent & Housing" or (is_person and cadence == "monthly" and typical >= RENT_MIN_AMOUNT):
        return "rent"
    if _EMI.search(text) or category == "Finance":
        return "emi"
    if _SIP.search(text) or category == "Investments":
        return "sip"
    if category in _BILL_CATEGORIES:
        return "bill"
    if category in _SUBSCRIPTION_CATEGORIES:
        return "subscription"
    return "other"


def _status(last: date, next_expected: date, cadence: str, today: date) -> str:
    _, _, nominal, _, tolerance = CADENCES[cadence]
    if (today - last).days > nominal * CANCELLED_AFTER:
        return "cancelled"
    if today > next_expected + timedelta(days=tolerance):
        return "missed"
    return "active"


def series_key(txn: Transaction) -> tuple[str, str, bool]:
    """(key, display name, is_person). People are keyed by their (merge-resolved) person id."""
    identity = person_identity(txn)
    if identity:
        vpa, name = identity
        key = f"person:{txn.person_id}" if txn.person_id else f"person:{person_key(identity)}"
        return key, (name.title() if name else vpa), True
    key = merchant_key(txn)
    return f"merchant:{key}", (txn.merchant_clean or key.title() or "Unknown"), False


def detect_series(txns: list[Transaction], today: date) -> list[Detected]:
    groups: dict[str, list[Transaction]] = {}
    names: dict[str, tuple[str, bool]] = {}
    for t in txns:
        if t.direction != TransactionDirection.debit or t.kind != TransactionKind.spend:
            continue
        key, name, is_person = series_key(t)
        if key.endswith(":"):
            continue
        groups.setdefault(key, []).append(t)
        names[key] = (name, is_person)

    found = []
    for key, group in groups.items():
        group.sort(key=lambda t: t.transaction_date)
        best = None
        for cadence, (_, _, _, min_n, _) in CADENCES.items():
            run = _trailing_run(group, cadence)
            # drop the oldest payments until the amounts are steady
            while len(run) >= min_n and _amount_profile([t.amount for t in run]) is None:
                run = run[1:]
            if len(run) < min_n:
                continue
            if cadence == "yearly" and abs(run[-1].transaction_date.day - run[-2].transaction_date.day) > 3:
                continue  # yearly needs the same date each year
            if best is None or len(run) > len(best[1]):
                best = (cadence, run)
        if not best:
            continue
        cadence, run = best
        typical, previous = _amount_profile([t.amount for t in run])
        last = run[-1].transaction_date.date()
        nxt = next_date(last, cadence)
        name, is_person = names[key]
        found.append(Detected(
            key=key, display_name=name[:100], cadence=cadence, typical_amount=typical,
            last_amount=run[-1].amount, last_date=last, next_expected=nxt, occurrences=len(run),
            status=_status(last, nxt, cadence, today),
            type_guess=_type_guess(run, cadence, is_person, typical),
            previous_amount=previous, category=run[-1].category,
            established_on=run[CADENCES[cadence][3] - 1].transaction_date.date(),
        ))
    return found


def sync_series(db: Session, user: User, txns: list[Transaction], today: date) -> None:
    """Upsert detected series; keep user fields. Undetected series go unless the user acted on them."""
    detected = {d.key: d for d in detect_series(txns, today)}
    existing = {s.key: s for s in db.query(RecurringSeries).filter(RecurringSeries.user_id == user.id)}
    for key, d in detected.items():
        row = existing.get(key) or RecurringSeries(user_id=user.id, key=key)
        for field in Detected.__dataclass_fields__:
            setattr(row, field, getattr(d, field))
        db.add(row)
    for key, row in existing.items():
        if key not in detected:
            if row.user_status or row.usage or row.user_name or row.user_type:
                row.status = _status(row.last_date, row.next_expected, row.cadence, today)
            else:
                db.delete(row)
