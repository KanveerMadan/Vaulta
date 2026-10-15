"""
Which sources feed a user's numbers (home "coverage" card, onboarding meter).

  statements  date range of imported statement history (not alerts or manual entries)
  email       bank alerts forwarded; stale when connected but none parsed in STALE_AFTER
  telegram    chat linked
  cash        any cash movement logged or a cash count declared
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import Date, cast, func
from sqlalchemy.orm import Session

from app.core import clock
from app.models.cash import CashDeclaration
from app.models.inbound import InboundEvent
from app.models.transaction import Transaction
from app.models.transaction_source import StatementSourceType, TransactionSourceRecord
from app.models.user import User

STALE_AFTER = timedelta(days=7)
# Tracking coverage meter (onboarding): points per part, out of 100
METER = {"basics": 10, "statements": 30, "email": 25, "telegram": 10, "review": 25}
HISTORY_TARGET_MONTHS = 3        # full statement points at 3 months of history
REVIEW_POINTS_PER_OPEN_CARD = 5
NOT_STATEMENTS = (StatementSourceType.email_alert, StatementSourceType.manual)


def _months(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1


def sources(db: Session, user: User) -> dict:
    day = func.coalesce(TransactionSourceRecord.raw_date, cast(TransactionSourceRecord.raw_timestamp, Date))
    first, last = (db.query(func.min(day), func.max(day))
                   .filter(TransactionSourceRecord.user_id == user.id, TransactionSourceRecord.source.notin_(NOT_STATEMENTS))
                   .one())
    last_alert = (db.query(func.max(InboundEvent.received_at))
                  .filter(InboundEvent.user_id == user.id, InboundEvent.outcome == "parsed").scalar())
    has_cash = (db.query(Transaction.id).filter(Transaction.user_id == user.id, Transaction.cash_flow.isnot(None)).first()
                or db.query(CashDeclaration.id).filter(CashDeclaration.user_id == user.id).first()) is not None
    email_stale = last_alert is not None and clock.now() - last_alert > STALE_AFTER
    out = {
        "statements": {"active": first is not None, "from": first.isoformat() if first else None,
                       "to": last.isoformat() if last else None, "months": _months(first, last) if first else 0},
        "email": {"active": last_alert is not None and not email_stale, "connected": last_alert is not None,
                  "last_at": last_alert.isoformat() if last_alert else None, "stale": email_stale},
        "telegram": {"active": user.telegram_chat_id is not None},
        "cash": {"active": has_cash},
    }
    # what to fix on the Connect page: never-set-up statements/email, or alerts that went quiet
    out["needs_attention"] = [k for k in ("statements", "email") if not out[k]["active"]]
    return out


def meter(user: User, src: dict, open_reviews: int, email_verified: bool = False) -> dict:
    """Tracking coverage %: sources set up, history length and review completion."""
    basics = bool((user.onboarding or {}).get("basics_done"))
    has_data = src["statements"]["active"] or src["email"]["connected"]
    parts = {
        "basics": METER["basics"] if basics else 0,
        "statements": round(METER["statements"] * min(src["statements"]["months"], HISTORY_TARGET_MONTHS) / HISTORY_TARGET_MONTHS),
        "email": METER["email"] if src["email"]["active"] or email_verified else 0,
        "telegram": METER["telegram"] if src["telegram"]["active"] else 0,
        "review": max(METER["review"] - REVIEW_POINTS_PER_OPEN_CARD * open_reviews, 0) if has_data else 0,
    }
    return {"percent": sum(parts.values()), "parts": parts, "max": METER}
