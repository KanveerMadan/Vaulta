"""
People (P2P UPI).

  GET   /api/people        people with totals, tags and lent/borrowed balances
  PATCH /api/people/{id}   rename, tag, default category/kind (re-applied to
                           past and future transactions unless individually corrected)
  POST  /api/people/{id}/merge  {"source_id": ...} fold another person into this one
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import clock
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.person import Person
from app.models.transaction import Transaction, TransactionKind
from app.models.transaction_source import TransactionDirection
from app.models.user import User
from app.schemas.people import PeopleList, PersonMerge, PersonResponse, PersonUpdate
from app.services.detection import run_detection
from app.services.people import balances, merge_people, resolve, set_tag

router = APIRouter(prefix="/api/people", tags=["people"])


def _views(db: Session, user: User, only: uuid.UUID | None = None) -> list[PersonResponse]:
    people = db.query(Person).filter(Person.user_id == user.id, Person.merged_into_id.is_(None)).all()
    txns = db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.person_id.isnot(None)).all()
    bal = balances(txns)
    today = clock.today()
    out = []
    for p in people:
        if only and p.id != only:
            continue
        mine = [t for t in txns if t.person_id == p.id and t.kind != TransactionKind.reversal]
        if not mine:
            continue
        b = bal.get(p.id)
        paid = sum((t.amount for t in mine if t.direction == TransactionDirection.debit), Decimal("0.00"))
        received = sum((t.amount for t in mine if t.direction == TransactionDirection.credit), Decimal("0.00"))
        out.append(PersonResponse(
            id=p.id, name=p.display_name, masked_vpa=p.masked_vpa, tag=p.tag,
            default_category=p.default_category, default_kind=p.default_kind,
            paid_total=paid, received_total=received, transaction_count=len(mine),
            last_date=max(t.transaction_date for t in mine).date(),
            owed_to_you=b.owed_to_you if b else Decimal("0.00"), you_owe=b.you_owe if b else Decimal("0.00"),
            balance=b.net if b else Decimal("0.00"),
            outstanding_days=(today - b.oldest_open).days if b and b.oldest_open else None,
        ))
    return sorted(out, key=lambda v: (-(v.paid_total + v.received_total)))


@router.get("", response_model=PeopleList)
def list_people(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return PeopleList(people=_views(db, current_user))


@router.patch("/{person_id}", response_model=PersonResponse)
def update_person(
    person_id: uuid.UUID,
    payload: PersonUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    person = db.query(Person).filter(Person.id == person_id, Person.user_id == current_user.id).first()
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")
    fields = payload.model_fields_set
    if "display_name" in fields:
        person.display_name = payload.display_name
    if "tag" in fields:
        set_tag(person, payload.tag)
    if "default_category" in fields:
        person.default_category = payload.default_category
    if "default_kind" in fields:
        person.default_kind = payload.default_kind
    db.commit()
    run_detection(db, current_user)
    return _views(db, current_user, only=person.id)[0]


@router.post("/{person_id}/merge", response_model=PersonResponse)
def merge_person(
    person_id: uuid.UUID,
    payload: PersonMerge,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Merge `source_id` into this person: their transactions, tag and balance move here."""
    mine = {p.id: p for p in db.query(Person).filter(Person.user_id == current_user.id)}
    target, source = mine.get(person_id), mine.get(payload.source_id)
    if target is None or source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")
    if resolve(target, mine).id == resolve(source, mine).id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="These are already the same person.")
    merge_people(resolve(source, mine), resolve(target, mine))
    db.commit()
    run_detection(db, current_user)
    return _views(db, current_user, only=resolve(target, mine).id)[0]
