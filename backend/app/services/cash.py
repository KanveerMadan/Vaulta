"""
Cash wallet.

  withdrawal  an ATM / cash withdrawal debit → kind=transfer into the wallet (not spending)
  spend       a cash payment (manual entry, quick add, Telegram with "cash") → spending, out of the wallet
  received    cash received (manual credit with "cash") → into the wallet

The latest declaration ("I have ₹X now") is the baseline:
  balance     = declared + withdrawn + received − spent   (since the declaration)
  unaccounted = withdrawn + received − spent              (cash that came out but isn't logged or confirmed)
Reconciling: "still have it" declares the balance; allocating or "untracked
misc" records the unaccounted amount as a cash spend, so totals stay honest.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core import clock
from app.models.cash import CashDeclaration
from app.models.transaction import Transaction, TransactionKind
from app.models.transaction_source import StatementSourceType, TransactionDirection
from app.models.user import User
from app.services import analytics

# ── Tunable (listed in the Phase 4 report) ────────────────────────────────────
ATM_PATTERN = re.compile(r"\bATM\b|\bATW\b|\bNFS\b|\bCWDR?\b|CASH\s*WDL|CASH\s*WITHDRAW|ATM\s*WDL|\bWDL\b.*\bATM", re.I)
RECONCILE_THRESHOLD = Decimal("200")
MISC_CATEGORY = "Misc cash"
RECONCILED_MERCHANT = "Cash (reconciled)"


def paid_in_cash(t: Transaction) -> bool:
    return any(r.source == StatementSourceType.manual and isinstance(r.raw_row, dict) and r.raw_row.get("payment_method") == "cash"
               for r in t.source_records)


def classify(ctx) -> None:
    """Detection step: mark cash movements; ATM withdrawals become transfers (unless the user said otherwise)."""
    for t in ctx.txns:
        t.cash_flow = None
        if t.direction == TransactionDirection.debit and ATM_PATTERN.search(t.merchant_raw or "") and not paid_in_cash(t):
            if ctx.is_locked(t, "kind") and t.kind != TransactionKind.transfer:
                continue
            ctx.set_kind(t, TransactionKind.transfer)
            t.cash_flow = "withdrawal"
        elif paid_in_cash(t) and t.kind != TransactionKind.reversal:
            t.cash_flow = "spend" if t.direction == TransactionDirection.debit else "received"


def last_declaration(db: Session, user_id: uuid.UUID) -> Optional[CashDeclaration]:
    return (db.query(CashDeclaration).filter(CashDeclaration.user_id == user_id)
            .order_by(CashDeclaration.declared_at.desc()).first())


def _after(t: Transaction, decl: CashDeclaration) -> bool:
    """
    Did this movement happen after the declaration? By transaction date (a
    statement imported today can carry last month's ATM withdrawal, which the
    declaration already covers); on the declaration's own day, by when it was logged.
    """
    day, decl_day = t.transaction_date.date(), decl.declared_at.astimezone(timezone.utc).date()
    return day > decl_day or (day == decl_day and t.created_at > decl.declared_at)


def _item(t: Transaction) -> dict:
    # never the narration: the wallet goes to the chat assistant and reports
    label = t.merchant_clean or ("ATM withdrawal" if t.cash_flow == "withdrawal" else "Cash")
    return {"date": t.transaction_date.date().isoformat(), "merchant": label,
            "amount": analytics.money(t.amount), "category": t.category}


def wallet(db: Session, user_id: uuid.UUID) -> dict:
    decl = last_declaration(db, user_id)
    moves = (db.query(Transaction).filter(Transaction.user_id == user_id, Transaction.cash_flow.isnot(None),
                                          Transaction.split_parent_id.is_(None))
             .order_by(Transaction.transaction_date.desc()).all())
    if decl:
        moves = [t for t in moves if _after(t, decl)]

    def total(flow: str) -> Decimal:
        return analytics.money(sum((t.amount for t in moves if t.cash_flow == flow), analytics.ZERO))

    withdrawn, received, spent = total("withdrawal"), total("received"), total("spend")
    declared = analytics.money(decl.amount) if decl else analytics.ZERO
    return {
        "balance": declared + withdrawn + received - spent,
        "declared": declared, "declared_at": decl.declared_at.isoformat() if decl else None,
        "since": decl.declared_at.date().isoformat() if decl else None,
        "withdrawn": withdrawn, "received": received, "spent": spent,
        "unaccounted": withdrawn + received - spent,
        "withdrawals": [_item(t) for t in moves if t.cash_flow == "withdrawal"][:20],
        "spends": [_item(t) for t in moves if t.cash_flow == "spend"][:20],
    }


def declare(db: Session, user: User, amount: Decimal, reason: str = "declared") -> dict:
    """Record cash in hand. Returns the gap (expected − declared) the user may want to allocate."""
    before = wallet(db, user.id)
    db.add(CashDeclaration(user_id=user.id, amount=amount, reason=reason, declared_at=clock.now()))
    db.commit()
    return {"expected": before["balance"], "declared": amount, "gap": before["balance"] - amount}


def record_cash_spend(db: Session, user: User, amount: Decimal, category: str) -> None:
    from app.schemas.transaction import ManualTransactionCreate
    from app.services.transaction_service import create_manual_transaction   # transaction_service → detection → this module
    create_manual_transaction(db, user, ManualTransactionCreate(
        client_id=str(uuid.uuid4()), date=clock.today().isoformat(), amount=f"{amount:.2f}",
        merchant=RECONCILED_MERCHANT, category=category, payment_method="cash"))


def reconcile(db: Session, user: User, action: str, category: Optional[str] = None, amount: Optional[Decimal] = None) -> str:
    """
    action: "have" (still have it), "misc" (untracked, Misc cash), "category" (allocate to `category`).
    amount defaults to what's unaccounted now.
    """
    w = wallet(db, user.id)
    amount = analytics.money(amount if amount is not None else w["unaccounted"])
    if amount <= 0:
        return "Nothing to reconcile."
    if action == "have":
        declare(db, user, w["balance"], reason="still_have")
        return f"Noted: you still have {analytics.money(w['balance'])} in cash."
    record_cash_spend(db, user, amount, MISC_CATEGORY if action == "misc" else category)
    return f"Recorded {amount} of cash spending under {MISC_CATEGORY if action == 'misc' else category}."


def last_week_end(user: User) -> date:
    """The most recent Sunday that has fully ended, in the user's timezone."""
    today = clock.now().astimezone(clock.zone(user.timezone)).date()
    return today - timedelta(days=(today.weekday() + 1) % 7 or 7)


def needs_reconciliation(db: Session, user: User) -> Optional[dict]:
    """{amount, week_end} when > ₹200 is unaccounted and nothing was reconciled since the week ended."""
    w = wallet(db, user.id)
    week_end = last_week_end(user)
    end_of_week = datetime.combine(week_end + timedelta(days=1), datetime.min.time(), tzinfo=clock.zone(user.timezone))
    decl = last_declaration(db, user.id)
    reconciled_since = decl and decl.declared_at >= end_of_week.astimezone(timezone.utc)
    if w["unaccounted"] > RECONCILE_THRESHOLD and not reconciled_since:
        return {"amount": w["unaccounted"], "week_end": week_end}
    return None
