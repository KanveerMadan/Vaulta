"""
Savings goals.

  GET    /api/goals                                  every goal with its status (analytics.goal_status)
  POST   /api/goals                                  {name, target_amount, target_date, category?}
  PATCH  /api/goals/{goal_id}                        any of those fields
  DELETE /api/goals/{goal_id}
  POST   /api/goals/{goal_id}/entries                {amount, date?} money put towards it (negative takes it out)
  DELETE /api/goals/{goal_id}/entries/{entry_id}
"""

import json
import uuid
from datetime import date
from datetime import date as Date   # EntryCreate has a field called date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.core import clock
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.goal import Goal, GoalEntry
from app.models.user import User
from app.schemas.transaction import CATEGORIES
from app.services import analytics
from app.services.goals import add_entry, create_goal

router = APIRouter(prefix="/api/goals", tags=["goals"])


class GoalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    target_amount: Optional[Decimal] = Field(default=None, gt=0, le=Decimal("100000000"), decimal_places=2)
    target_date: Optional[date] = None
    category: Optional[str] = None      # the category to cut; null clears it

    @field_validator("category")
    @classmethod
    def known_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in CATEGORIES:
            raise ValueError("Unknown category")
        return v


class GoalCreate(GoalUpdate):
    name: str = Field(min_length=1, max_length=80)
    target_amount: Decimal = Field(gt=0, le=Decimal("100000000"), decimal_places=2)
    target_date: date


class EntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(decimal_places=2, ge=Decimal("-100000000"), le=Decimal("100000000"))
    date: Optional[Date] = None

    @field_validator("amount")
    @classmethod
    def not_zero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("amount can't be zero")
        return v


def _owned(db: Session, user: User, goal_id: uuid.UUID) -> Goal:
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")
    return goal


def _json(value):
    return json.loads(json.dumps(value, default=str))   # Decimals as strings


def _view(db: Session, goal: Goal) -> dict:
    return _json(analytics.goal_status(db, goal, analytics.monthly_savings_estimate(db, goal.user_id)))


@router.get("")
def list_goals(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"items": _json(analytics.goals_overview(db, current_user.id))}


@router.post("", status_code=status.HTTP_201_CREATED)
def new_goal(payload: GoalCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.target_date <= clock.today():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The target date must be in the future.")
    return _view(db, create_goal(db, current_user, payload.name, payload.target_amount, payload.target_date, payload.category))


@router.patch("/{goal_id}")
def update_goal(goal_id: uuid.UUID, payload: GoalUpdate, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    goal = _owned(db, current_user, goal_id)
    if payload.target_date is not None and payload.target_date <= clock.today():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The target date must be in the future.")
    for field in payload.model_fields_set:
        value = getattr(payload, field)
        if value is None and field != "category":
            continue
        setattr(goal, field, value.strip() if field == "name" else value)
    db.commit()
    return _view(db, goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_owned(db, current_user, goal_id))
    db.commit()


@router.post("/{goal_id}/entries", status_code=status.HTTP_201_CREATED)
def contribute(goal_id: uuid.UUID, payload: EntryCreate, current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    goal = _owned(db, current_user, goal_id)
    day = payload.date or clock.today()
    if day > clock.today():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The date can't be in the future.")
    add_entry(db, goal, payload.amount, day)
    return _view(db, goal)


@router.delete("/{goal_id}/entries/{entry_id}")
def remove_entry(goal_id: uuid.UUID, entry_id: uuid.UUID, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    goal = _owned(db, current_user, goal_id)
    entry = db.query(GoalEntry).filter(GoalEntry.id == entry_id, GoalEntry.goal_id == goal.id).first()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found.")
    db.delete(entry)
    db.commit()
    db.refresh(goal)
    return _view(db, goal)
