"""
In-app alerts (the bell).

  GET  /api/alerts         latest alerts and the unread count
  POST /api/alerts/read    {"ids": [...]} marks those read; no ids marks all read
Per-type, per-channel choices and quiet hours live in /api/settings.
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core import clock
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.alert import Alert
from app.models.user import User

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

LIST_LIMIT = 50


class AlertView(BaseModel):
    id: uuid.UUID
    type: str
    message: str
    created_at: str
    read: bool


class AlertList(BaseModel):
    unread: int
    items: List[AlertView]


class MarkRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: Optional[List[uuid.UUID]] = Field(default=None, max_length=200)


def _list(db: Session, user: User) -> AlertList:
    mine = db.query(Alert).filter(Alert.user_id == user.id)
    rows = mine.order_by(Alert.created_at.desc()).limit(LIST_LIMIT).all()
    return AlertList(unread=mine.filter(Alert.read_at.is_(None)).count(),
                     items=[AlertView(id=a.id, type=a.type, message=a.message, created_at=a.created_at.isoformat(),
                                      read=a.read_at is not None) for a in rows])


@router.get("", response_model=AlertList)
def list_alerts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _list(db, current_user)


@router.post("/read", response_model=AlertList)
def mark_read(payload: MarkRead, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Alert).filter(Alert.user_id == current_user.id, Alert.read_at.is_(None))
    if payload.ids is not None:
        q = q.filter(Alert.id.in_(payload.ids))
    q.update({Alert.read_at: clock.now()}, synchronize_session=False)
    db.commit()
    return _list(db, current_user)
