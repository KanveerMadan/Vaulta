"""
The guided tour and the getting-started checklist (services/getting_started.py).

  GET   /api/tour         {available, status, step}
  PATCH /api/tour         {status?, step?}: start, advance, finish or skip; status "active" replays from step 0
  GET   /api/checklist    {available, items: [{id, title, link, done}], done, total, percent, dismissed}
  PATCH /api/checklist    {dismissed}: hide it, or bring it back (Settings)
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import getting_started

router = APIRouter(tags=["getting started"])


class TourUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Optional[Literal["active", "done", "skipped"]] = None
    step: Optional[int] = Field(default=None, ge=0, le=20)

    @model_validator(mode="after")
    def something(self):
        if self.status is None and self.step is None:
            raise ValueError("Send status and/or step")
        return self


class ChecklistUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    dismissed: bool


def _verified(user: User) -> bool:
    return bool(getattr(getattr(user, "token", None), "email_verified", False))


@router.get("/api/tour")
def get_tour(user: User = Depends(get_current_user)):
    return getting_started.tour(user)


@router.patch("/api/tour")
def update_tour(payload: TourUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return getting_started.set_tour(db, user, payload.status, payload.step)


@router.get("/api/checklist")
def get_checklist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return getting_started.checklist(db, user, _verified(user))


@router.patch("/api/checklist")
def update_checklist(payload: ChecklistUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    getting_started.set_checklist(db, user, payload.dismissed)
    return getting_started.checklist(db, user, _verified(user))
