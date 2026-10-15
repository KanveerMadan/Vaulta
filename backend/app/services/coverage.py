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
