"""
Detection pipeline: derives each transaction's kind (and links between
transactions) from defaults plus signals in the user's whole history.

run_detection() recomputes from scratch every time, so it is idempotent and
undoing an input (a deleted rule, a dismissed tag) undoes its effect. A field
the user corrected (see models/correction.py) is never changed.

Order: defaults → failed-UPI reversals → own-account transfers → refunds →
people (link + tag defaults) → recurring series.

ponytail: loads all of a user's transactions into memory per run. Fine for
thousands of rows; batch by date window if users reach hundreds of thousands.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session, selectinload

from app.models.correction import Correction
from app.models.transaction import Transaction, TransactionKind, TransactionNature
from app.models.transaction_source import StatementSourceType, TransactionDirection
from app.models.user import User
from app.services.dedup_matcher import _merchant_overlap
from app.services.people import apply_person_defaults, link_people
from app.services.recurring import sync_series

# ── Tunable thresholds (listed in the Phase 2 report) ─────────────────────────
TRANSFER_WINDOW = timedelta(days=3)
# Pairs with no transfer signal on either side must be at least this large;
# below it, equal amounts across accounts are too often coincidence.
MIN_UNSIGNALLED_TRANSFER = Decimal("1000")

TRANSFER_PATTERN = re.compile(
    r"\bSELF\b|TRANSFER\s+TO\s+OWN|OWN\s+A/?C|\bCC\s*PAYMENT|CREDIT\s*CARD\s*(BILL\s*)?PAYMENT|"
    r"CARD\s*BILL|AUTOPAY|\bCRED\b|PAYMENT\s+RECEIVED",
    re.IGNORECASE,
)

REVERSAL_WINDOW = timedelta(days=7)
REFUND_WINDOW = timedelta(days=60)

REVERSAL_PATTERN = re.compile(r"REVERS|\bREV\b|\bFAILED\b|\bDECLINED\b|\bRET\b", re.IGNORECASE)
REFUND_PATTERN = re.compile(r"REFUND|\bRFND\b|REVERSAL", re.IGNORECASE)

_TRANSFER_GROUP_NS = uuid.UUID("6f1d3b1e-2b8f-4f7e-9a40-6a7d0c2f5e11")


def _key(source, label) -> tuple:
    return (source.value if hasattr(source, "value") else source, label)


@dataclass
class Ctx:
    txns: list[Transaction]
    locked: set[tuple[uuid.UUID, str]]
    review_transfer_ids: list[uuid.UUID] = field(default_factory=list)

    def is_locked(self, txn: Transaction, f: str) -> bool:
        return (txn.id, f) in self.locked

    def set_kind(self, txn: Transaction, kind: TransactionKind) -> None:
        if not self.is_locked(txn, "kind"):
            txn.kind = kind

    def set_category(self, txn: Transaction, category: Optional[str]) -> None:
        if not self.is_locked(txn, "category"):
            txn.category = category

    def auto_kind(self, txn: Transaction, *kinds: TransactionKind) -> bool:
        """True if detection may still decide this transaction's kind and it's currently one of `kinds`."""
        return not self.is_locked(txn, "kind") and txn.kind in kinds


def default_kind(txn: Transaction) -> TransactionKind:
    if txn.transaction_nature == TransactionNature.self_transfer:
        return TransactionKind.transfer
    return TransactionKind.spend if txn.direction == TransactionDirection.debit else TransactionKind.income


def accounts(txn: Transaction) -> set[tuple]:
    """Account keys this transaction was seen in. Manual entries have none."""
    return {_key(r.source, r.source_label) for r in txn.source_records if r.source != StatementSourceType.manual}


def has_transfer_signal(txn: Transaction) -> bool:
    return txn.transaction_nature == TransactionNature.self_transfer or bool(TRANSFER_PATTERN.search(txn.merchant_raw or ""))


def _day(txn: Transaction):
    return txn.transaction_date.date()


# ── Steps ─────────────────────────────────────────────────────────────────────

def references(txn: Transaction) -> set[str]:
    """UTRs and statement references seen for this transaction."""
    refs = {r.utr for r in txn.source_records if r.utr}
    refs |= {r.raw_row.get("reference") for r in txn.source_records if isinstance(r.raw_row, dict) and r.raw_row.get("reference")}
    return refs


def _reset(ctx: Ctx) -> None:
    for t in ctx.txns:
        ctx.set_kind(t, default_kind(t))
        ctx.set_category(t, t.auto_category)
        t.transfer_group_id = None
        t.refund_of_id = None


def _reversals(ctx: Ctx) -> None:
    """
    Failed UPI: a debit, then a credit of the same amount within 7 days that
    shares its UTR/reference, or whose narration says reversal/failed.
    Both become kind=reversal; the credit links to the debit.
    """
    taken: set[uuid.UUID] = set()
    for c in ctx.txns:
        if c.direction != TransactionDirection.credit or not ctx.auto_kind(c, TransactionKind.income):
            continue
        c_refs = references(c)
        says_reversal = bool(REVERSAL_PATTERN.search(c.merchant_raw or ""))
        if not c_refs and not says_reversal:
            continue
        candidates = [
            d for d in ctx.txns
            if d.direction == TransactionDirection.debit and d.id not in taken
            and ctx.auto_kind(d, TransactionKind.spend)
            and d.amount == c.amount and timedelta(0) <= _day(c) - _day(d) <= REVERSAL_WINDOW
        ]
        same_ref = [d for d in candidates if c_refs & references(d)]
        chosen = same_ref or (candidates if says_reversal else [])
        if not chosen:
            continue
        d = max(chosen, key=lambda t: t.transaction_date)  # nearest earlier debit
        for t in (d, c):
            ctx.set_kind(t, TransactionKind.reversal)
        c.refund_of_id = d.id
        taken.add(d.id)


def _same_merchant(a: Transaction, b: Transaction) -> bool:
    if a.merchant_clean and b.merchant_clean:
        return a.merchant_clean.lower() == b.merchant_clean.lower()
    return False


def _refunds(ctx: Ctx) -> None:
    """
    A credit is a refund when its narration says so, or when it comes from the
    same normalized merchant as an earlier spend within 60 days and is no more
    than what's left of that spend after earlier refunds (partial refunds
    allowed). Linked refunds take the original's category and merchant, so
    spending for that merchant and category is netted.
    """
    remaining: dict[uuid.UUID, Decimal] = {}
    for c in ctx.txns:
        if c.direction != TransactionDirection.credit or not ctx.auto_kind(c, TransactionKind.income):
            continue
        says_refund = bool(REFUND_PATTERN.search(c.merchant_raw or ""))
        originals = [
            d for d in ctx.txns
            if d.direction == TransactionDirection.debit and d.kind == TransactionKind.spend
            and timedelta(0) <= _day(c) - _day(d) <= REFUND_WINDOW
            and remaining.get(d.id, d.amount) >= c.amount
            and (_same_merchant(c, d) or (says_refund and _token_overlap(c, d)))
        ]
        if not originals and not says_refund:
            continue
        ctx.set_kind(c, TransactionKind.refund)
        if originals:
            d = max(originals, key=lambda t: t.transaction_date)  # most recent purchase
            remaining[d.id] = remaining.get(d.id, d.amount) - c.amount
            c.refund_of_id = d.id
            ctx.set_category(c, d.category)
            if not c.merchant_clean:
                c.merchant_clean = d.merchant_clean


_REFUND_NOISE = {"refund", "rfnd", "reversal", "upi", "neft", "imps"}


def _merchant_words(t: Transaction) -> str:
    words = re.split(r"[^a-z0-9]+", (t.merchant_clean or t.merchant_raw or "").lower())
    return " ".join(w for w in words if w not in _REFUND_NOISE)


def _token_overlap(a: Transaction, b: Transaction) -> bool:
    return _merchant_overlap(_merchant_words(a), _merchant_words(b))


def _transfer_eligible(ctx: Ctx, t: Transaction) -> bool:
    if ctx.is_locked(t, "kind"):
        return t.kind == TransactionKind.transfer
    return t.kind in (TransactionKind.spend, TransactionKind.income, TransactionKind.transfer)


def find_transfer_pairs(ctx: Ctx) -> tuple[list[tuple[Transaction, Transaction]], list[Transaction]]:
    """
    A debit in one account and a credit of the same amount in a different
    account within TRANSFER_WINDOW. Only mutually unique pairs are accepted;
    ambiguous or one-sided candidates that carry a transfer signal are
    returned for review instead of being guessed.
    """
    debits = [t for t in ctx.txns if t.direction == TransactionDirection.debit and accounts(t) and _transfer_eligible(ctx, t)]
    credits = [t for t in ctx.txns if t.direction == TransactionDirection.credit and accounts(t) and _transfer_eligible(ctx, t)]

    def matches(d: Transaction, c: Transaction) -> bool:
        if d.amount != c.amount or abs(_day(d) - _day(c)) > TRANSFER_WINDOW:
            return False
        if accounts(d) & accounts(c):
            return False
        return has_transfer_signal(d) or has_transfer_signal(c) or d.amount >= MIN_UNSIGNALLED_TRANSFER

    options: dict[uuid.UUID, list[Transaction]] = {}
    for d in debits:
        for c in credits:
            if matches(d, c):
                options.setdefault(d.id, []).append(c)
                options.setdefault(c.id, []).append(d)

    pairs, paired = [], set()
    for d in debits:
        cs = options.get(d.id, [])
        if len(cs) == 1 and len(options[cs[0].id]) == 1:
            pairs.append((d, cs[0]))
            paired.update({d.id, cs[0].id})

    one_sided = [
        t for t in debits + credits
        if t.id not in paired and has_transfer_signal(t) and t.kind != TransactionKind.transfer
        and not ctx.is_locked(t, "kind")
    ]
    return pairs, one_sided


def _transfers(ctx: Ctx) -> None:
    pairs, one_sided = find_transfer_pairs(ctx)
    for d, c in pairs:
        group = uuid.uuid5(_TRANSFER_GROUP_NS, "|".join(sorted([str(d.id), str(c.id)])))
        for t in (d, c):
            ctx.set_kind(t, TransactionKind.transfer)
            t.transfer_group_id = group
    ctx.review_transfer_ids = [t.id for t in one_sided]


# ── Entry point ───────────────────────────────────────────────────────────────

def load_context(db: Session, user: User) -> Ctx:
    txns = (
        db.query(Transaction)
        .options(selectinload(Transaction.source_records))
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.transaction_date, Transaction.created_at)
        .all()
    )
    locked = {
        (tid, f) for tid, f in db.query(Correction.transaction_id, Correction.field).filter(Correction.user_id == user.id)
    }
    return Ctx(txns=txns, locked=locked)


def run_detection(db: Session, user: User, today: Optional[date] = None) -> Ctx:
    ctx = load_context(db, user)
    _reset(ctx)
    _reversals(ctx)
    _transfers(ctx)
    _refunds(ctx)
    people = link_people(db, user, ctx.txns)
    apply_person_defaults(ctx, people)
    db.flush()
    sync_series(db, user, ctx.txns, today or date.today())
    db.commit()
    return ctx
