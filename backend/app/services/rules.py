"""
Learned rules. When the user's two most recent corrections of a field on two
different transactions from the same merchant agree, that becomes a rule:
merchant → value, applied to every past transaction the user didn't correct
individually, and to future ones.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.correction import Correction
from app.models.rule import Rule
from app.models.transaction import KIND_DIRECTIONS, Transaction, TransactionKind
from app.services.keys import merchant_key

LEARN_AFTER = 2          # consistent corrections needed (listed in the Phase 2 report)
RULE_FIELDS = ("category", "kind")


def apply_rules(ctx, rules: list[Rule]) -> None:
    by_key = {(r.merchant_key, r.field): r for r in rules}
    for t in ctx.txns:
        if t.person_id is not None:
            continue  # people are handled by person tags
        key = merchant_key(t)
        category = by_key.get((key, "category"))
        if category:
            ctx.set_category(t, category.value)
        kind_rule = by_key.get((key, "kind"))
        if kind_rule:
            kind = TransactionKind(kind_rule.value)
            if t.direction.value in KIND_DIRECTIONS[kind] and t.kind in (TransactionKind.spend, TransactionKind.income):
                ctx.set_kind(t, kind)


def learn_from(db: Session, txn: Transaction, field: str) -> Optional[Rule]:
    """Create/update a rule if this correction makes LEARN_AFTER consistent ones for the merchant."""
    if field not in RULE_FIELDS or txn.person_id is not None:
        return None
    key = merchant_key(txn)
    if not key:
        return None
    same_merchant = [
        t.id for t in db.query(Transaction).filter(Transaction.user_id == txn.user_id) if merchant_key(t) == key
    ]
    latest_per_txn: dict = {}
    for c in (
        db.query(Correction)
        .filter(Correction.user_id == txn.user_id, Correction.field == field, Correction.transaction_id.in_(same_merchant))
        .order_by(Correction.created_at.desc())
    ):
        latest_per_txn.setdefault(c.transaction_id, c)
    recent = sorted(latest_per_txn.values(), key=lambda c: c.created_at, reverse=True)[:LEARN_AFTER]
    if len(recent) < LEARN_AFTER or len({c.new_value for c in recent}) != 1 or recent[0].new_value is None:
        return None
    value = recent[0].new_value
    rule = db.query(Rule).filter(Rule.user_id == txn.user_id, Rule.merchant_key == key, Rule.field == field).first()
    if rule is None:
        rule = Rule(user_id=txn.user_id, merchant_key=key, field=field, origin="learned",
                    merchant_label=(txn.merchant_clean or key.title())[:100], value=value)
        db.add(rule)
    elif rule.value == value:
        return None  # nothing new learned
    rule.value = value
    db.flush()
    return rule
