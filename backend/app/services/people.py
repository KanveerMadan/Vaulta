"""
People (P2P): linking transactions to people, applying person tags, and
lent/borrowed balances. Called from services/detection.py.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.person import Person
from app.models.transaction import KIND_DIRECTIONS, Transaction, TransactionKind
from app.models.transaction_source import TransactionDirection
from app.models.user import User
from app.services.keys import person_identity, person_key

# What a tag means unless the user says otherwise (used by the People page and review answers)
TAG_DEFAULTS = {
    "Rent": ("Rent & Housing", "spend"),
    "Splits": ("Sent to People", "spend"),
    "Family": ("Sent to People", "spend"),
    "Friend": ("Sent to People", "spend"),
    "Lent": (None, "lent"),
    "Other": (None, None),
}


def link_people(db: Session, user: User, txns: list[Transaction]) -> dict[uuid.UUID, Person]:
    """Set person_id on every P2P transaction, creating people as first seen."""
    people = {p.key_hash: p for p in db.query(Person).filter(Person.user_id == user.id)}
    keys = {}
    for t in txns:
        identity = person_identity(t)
        keys[t.id] = person_key(identity) if identity else None
        if identity and keys[t.id] not in people:
            vpa, name = identity
            people[keys[t.id]] = Person(id=uuid.uuid4(), user_id=user.id, key_hash=keys[t.id],
                                        display_name=(name.title() if name else vpa)[:100], masked_vpa=vpa)
            db.add(people[keys[t.id]])
    db.flush()  # people exist before transactions point at them (no ORM relationship to order the flush)
    for t in txns:
        t.person_id = people[keys[t.id]].id if keys[t.id] else None
    return {p.id: p for p in people.values()}


def apply_person_defaults(ctx, people: dict[uuid.UUID, Person]) -> None:
    """A tagged person's default category/kind apply to their transactions unless individually corrected."""
    for t in ctx.txns:
        person = people.get(t.person_id)
        if person is None:
            continue
        if person.default_category:
            ctx.set_category(t, person.default_category)
        kind = person.default_kind and TransactionKind(person.default_kind)
        if kind and t.direction.value in KIND_DIRECTIONS[kind] and t.kind in (TransactionKind.spend, TransactionKind.income):
            ctx.set_kind(t, kind)


@dataclass
class Balance:
    owed_to_you: Decimal = Decimal("0")   # lent − repayments received
    you_owe: Decimal = Decimal("0")       # borrowed − repayments made
    oldest_open: Optional[date] = None    # oldest loan not yet repaid (either way)
    _open_lent: list = field(default_factory=list)
    _open_borrowed: list = field(default_factory=list)

    @property
    def net(self) -> Decimal:
        return self.owed_to_you - self.you_owe


def _settle(open_items: list, amount: Decimal) -> Decimal:
    """FIFO: pay off the oldest open items first. Returns what's left over."""
    while amount > 0 and open_items:
        when, left = open_items[0]
        used = min(left, amount)
        amount -= used
        if left - used > 0:
            open_items[0] = (when, left - used)
        else:
            open_items.pop(0)
    return amount


def balances(txns: list[Transaction]) -> dict[uuid.UUID, Balance]:
    result: dict[uuid.UUID, Balance] = {}
    for t in sorted(txns, key=lambda t: t.transaction_date):
        if t.person_id is None:
            continue
        b = result.setdefault(t.person_id, Balance())
        day = t.transaction_date.date()
        if t.kind == TransactionKind.lent:
            b._open_lent.append((day, t.amount))
        elif t.kind == TransactionKind.borrowed:
            b._open_borrowed.append((day, t.amount))
        elif t.kind == TransactionKind.repayment:
            _settle(b._open_lent if t.direction == TransactionDirection.credit else b._open_borrowed, t.amount)
    for b in result.values():
        b.owed_to_you = sum((a for _, a in b._open_lent), Decimal("0.00"))
        b.you_owe = sum((a for _, a in b._open_borrowed), Decimal("0.00"))
        dates = [d for d, _ in b._open_lent + b._open_borrowed]
        b.oldest_open = min(dates) if dates else None
    return result


def repayment_candidates(txns: list[Transaction]) -> list[Transaction]:
    """
    Transactions that look like a repayment: with a person who has an open
    loan the other way, after that loan, not already marked. Suggested in the
    review queue, never applied automatically.
    """
    open_since: dict[tuple, date] = {}
    out = []
    for t in sorted(txns, key=lambda t: t.transaction_date):
        if t.person_id is None:
            continue
        day = t.transaction_date.date()
        if t.kind == TransactionKind.lent:
            open_since.setdefault((t.person_id, "lent"), day)
        elif t.kind == TransactionKind.borrowed:
            open_since.setdefault((t.person_id, "borrowed"), day)
        elif t.kind in (TransactionKind.income, TransactionKind.spend):
            loan = "lent" if t.direction == TransactionDirection.credit else "borrowed"
            since = open_since.get((t.person_id, loan))
            if since and day >= since:
                out.append(t)
    open_people = {pid for pid, b in balances(txns).items() if b.owed_to_you > 0 or b.you_owe > 0}
    return [t for t in out if t.person_id in open_people]


def set_tag(person: Person, tag: Optional[str], default_category=..., default_kind=...) -> None:
    """Tag a person; the tag brings its defaults unless they're given explicitly."""
    person.tag = tag
    tag_category, tag_kind = TAG_DEFAULTS.get(tag, (None, None)) if tag else (None, None)
    person.default_category = tag_category if default_category is ... else default_category
    person.default_kind = tag_kind if default_kind is ... else default_kind
