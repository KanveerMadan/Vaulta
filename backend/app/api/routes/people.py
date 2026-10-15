"""
People (P2P UPI).

  GET   /api/people        people with totals, tags and lent/borrowed balances
  PATCH /api/people/{id}   rename, tag, default category/kind (re-applied to
                           past and future transactions unless individually corrected)
  POST  /api/people/{id}/merge  {"source_id": ...} fold another person into this one
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.person import Person
from app.models.user import User
from app.schemas.people import PeopleList, PersonMerge, PersonResponse, PersonUpdate
from app.services.detection import run_detection
from app.services import analytics
from app.services.people import merge_people, resolve, set_tag

router = APIRouter(prefix="/api/people", tags=["people"])


def _views(db: Session, user: User, only: uuid.UUID | None = None) -> list[PersonResponse]:
    views = analytics.person_balances(db, user.id)
    return [PersonResponse(**v) for v in views if only is None or v["id"] == str(only)]


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
