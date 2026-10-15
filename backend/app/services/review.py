"""
"Needs review" queue: one-tap questions whose answers fix the numbers.

Cards are built from current data on every request (nothing to keep in
sync); an answered card disappears because its answer changes the data
(a tag, a rule, a correction, a confirmed series). "Skip" is remembered in
review_dismissals.

Card ids are "<type>:<id>", stable across requests.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.person import Person
from app.models.recurring import RecurringSeries
from app.models.review import ReviewDismissal
from app.models.transaction import TransactionKind
from app.models.transaction_source import TransactionDirection
from app.models.user import User
from app.schemas.transaction import TransactionUpdate
from app.services import transaction_service
from app.services.budgets import SUGGESTION_MONTHS, create_or_reactivate, suggest_budgets
from app.services.detection import find_transfer_pairs, load_context, run_detection
from app.services.keys import merchant_key
from app.services.people import repayment_candidates, set_tag
from app.services.rules import upsert_rule

# ── Tunable thresholds (listed in the Phase 2 report) ─────────────────────────
PERSON_MIN_PAYMENTS = 3       # untagged person paid this many times → ask what it is
MERCHANT_SUGGESTIONS = 3      # category buttons on a "what is this merchant" card

SKIP = {"value": "skip", "label": "Skip"}


@dataclass
class Card:
    id: str
    type: str
    question: str
    detail: str
    options: list[dict]
    target: Any = None     # what an answer acts on: transaction, person, series, (merchant key, label)


def _rupees(v) -> str:
    v = Decimal(v)
    return f"₹{v:,.0f}" if v == v.to_integral() else f"₹{v:,.2f}"


def _times(n: int) -> str:
    return {1: "once", 2: "twice", 3: "three times"}.get(n, f"{n} times")


def build_cards(db: Session, user: User) -> list[Card]:
    ctx = load_context(db, user)
    cards: list[Card] = []

    # 1. One-sided transfer candidates
    _, one_sided = find_transfer_pairs(ctx)
    for t in one_sided:
        own = "transfer"
        other = "spend" if t.direction == TransactionDirection.debit else "income"
        cards.append(Card(
            id=f"transfer:{t.id}", type="transfer",
            question=f"{_rupees(t.amount)} {'to' if t.direction == TransactionDirection.debit else 'from'} "
                     f"“{t.merchant_clean or t.merchant_raw}”: a transfer between your own accounts?",
            detail="We only see one side of it. Transfers don't count as spending or income.",
            options=[{"value": own, "label": "Yes, my own account"},
                     {"value": other, "label": "No, it's " + ("spending" if other == "spend" else "income")}, SKIP],
            target=t,
        ))

    # 2. Repayment suggestions
    people = {p.id: p for p in db.query(Person).filter(Person.user_id == user.id)}
    for t in repayment_candidates(ctx.txns):
        name = people[t.person_id].display_name if t.person_id in people else "They"
        sent = "sent you" if t.direction == TransactionDirection.credit else "got"
        cards.append(Card(
            id=f"repayment:{t.id}", type="repayment",
            question=f"{name} {sent} {_rupees(t.amount)}. Is it a repayment?",
            detail="Repayments settle what was lent or borrowed and don't count as income or spending.",
            options=[{"value": "repayment", "label": "Yes, repayment"}, SKIP],
            target=t,
        ))

    # 3. Untagged people paid repeatedly
    paid: dict = {}
    for t in ctx.txns:
        if t.person_id and t.direction == TransactionDirection.debit and t.kind == TransactionKind.spend:
            paid.setdefault(t.person_id, []).append(t.amount)
    for pid, amounts in paid.items():
        person = people.get(pid)
        if person is None or person.tag or len(amounts) < PERSON_MIN_PAYMENTS:
            continue
        who = person.masked_vpa or person.display_name
        what = (f"{_rupees(amounts[0])} {_times(len(amounts))}" if len(set(amounts)) == 1
                else f"{_rupees(sum(amounts))} across {len(amounts)} payments")
        cards.append(Card(
            id=f"person:{pid}", type="person",
            question=f"Paid {who} {what}. What is it?", detail=person.display_name,
            options=[{"value": "Rent", "label": "Rent"}, {"value": "Splits", "label": "Split"},
                     {"value": "Lent", "label": "Lent"}, {"value": "Other", "label": "Other"}, SKIP],
            target=person,
        ))

    # 4. Newly detected recurring series
    for s in db.query(RecurringSeries).filter(RecurringSeries.user_id == user.id, RecurringSeries.user_status.is_(None),
                                              RecurringSeries.status != "cancelled"):
        cadence = {"weekly": "every week", "monthly": "every month", "yearly": "every year"}[s.cadence]
        cards.append(Card(
            id=f"recurring:{s.id}", type="recurring",
            question=f"{s.user_name or s.display_name}: {_rupees(s.typical_amount)} {cadence}. Track it as recurring?",
            detail=f"Seen {s.occurrences} times, last on {s.last_date:%d %b}.",
            options=[{"value": "confirmed", "label": "Yes, track it"}, {"value": "dismissed", "label": "Not recurring"}],
            target=s,
        ))

    # 5. Merchants with no category
    top_categories = [c for c, _ in Counter(t.category for t in ctx.txns
                                            if t.category and t.kind == TransactionKind.spend).most_common()]
    suggestions = (top_categories + ["Food & Dining", "Shopping", "Groceries"])
    suggestions = list(dict.fromkeys(suggestions))[:MERCHANT_SUGGESTIONS]
    unknown: dict[str, list] = {}
    for t in ctx.txns:
        if t.person_id is None and t.kind == TransactionKind.spend and not t.category and (t.id, "category") not in ctx.locked:
            unknown.setdefault(merchant_key(t), []).append(t)
    for key, txns in sorted(unknown.items(), key=lambda kv: -sum(t.amount for t in kv[1])):
        if not key:
            continue
        label = txns[0].merchant_clean or key.title()
        cards.append(Card(
            id=f"merchant:{hashlib.sha256(key.encode()).hexdigest()[:16]}", type="merchant",
            question=f"What is “{label}”?",
            detail=f"{_rupees(sum(t.amount for t in txns))} across {len(txns)} payment{'s' if len(txns) > 1 else ''}. "
                   f"Your answer applies to all of them and future ones.",
            options=[{"value": c, "label": c} for c in suggestions] + [{"value": "Other", "label": "Other"}, SKIP],
            target=(key, label),
        ))

    # 6. Anomalies: confirm they're fine, or leave them open (reports keep showing them)
    for a in db.query(Anomaly).filter(Anomaly.user_id == user.id, Anomaly.status == "open").order_by(Anomaly.occurred_on.desc()):
        d = a.details
        question = {
            "duplicate_charge": f"{d.get('merchant')} charged {_rupees(d.get('amount', 0))} twice within minutes. Expected?",
            "unusual_amount": f"{_rupees(d.get('amount', 0))} at {d.get('merchant')} is over 3× your usual {_rupees(d.get('typical', 0))}. Expected?",
            "category_spike": f"{d.get('category')} is {_rupees(d.get('amount', 0))}, well above your usual {_rupees(d.get('trailing_average', 0))}.",
            "unreversed_failed_upi": f"A failed {_rupees(d.get('amount', 0))} payment to {d.get('merchant')} hasn't been reversed yet.",
        }[a.type]
        cards.append(Card(
            id=f"anomaly:{a.id}", type="anomaly", question=question, detail=f"On {a.occurred_on:%d %b %Y}.",
            options=[{"value": "fine", "label": "It's fine"}, {"value": "skip", "label": "I'll check"}],
            target=a,
        ))

    # 7. Suggested budgets, once there are enough full months of history
    for category, limit, totals in suggest_budgets(db, user):
        cards.append(Card(
            id=f"budget:{category}", type="budget",
            question=f"Set a {_rupees(limit)} monthly budget for {category}?",
            detail=f"Your last {SUGGESTION_MONTHS} months: " + ", ".join(_rupees(t) for t in totals) + ".",
            options=[{"value": "set", "label": f"Set {_rupees(limit)}"}, {"value": "skip", "label": "Not now"}],
            target=(category, limit),
        ))

    dismissed = {d.card_id for d in db.query(ReviewDismissal).filter(ReviewDismissal.user_id == user.id)}
    return [c for c in cards if c.id not in dismissed]


def answer_card(db: Session, user: User, card: Card, answer: str) -> None:
    """Apply an answer (already checked against card.options)."""
    if answer == "skip":
        db.add(ReviewDismissal(user_id=user.id, card_id=card.id))
        db.commit()
    elif card.type in ("transfer", "repayment"):
        transaction_service.update_transaction(db, card.target, TransactionUpdate(kind=answer))
    elif card.type == "person":
        set_tag(card.target, answer)
        db.commit()
        run_detection(db, user)
    elif card.type == "recurring":
        card.target.user_status = answer
        db.commit()
    elif card.type == "merchant":
        key, label = card.target
        upsert_rule(db, user, key, label, "category", answer, "review")
    elif card.type == "anomaly":
        card.target.status = "dismissed"
        db.commit()
    elif card.type == "budget":
        category, limit = card.target
        create_or_reactivate(db, user, category, limit)
