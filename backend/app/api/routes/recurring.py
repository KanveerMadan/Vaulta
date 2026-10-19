"""
Recurring payments.

  GET   /api/recurring        series, monthly committed total, next 14 days
  PATCH /api/recurring/{id}   confirm/dismiss, rename, retype, keep/review
  POST  /api/recurring/refresh  re-run detection now
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.recurring import RecurringSeries
from app.models.user import User
from app.schemas.recurring import RecurringOverview, RecurringSeriesResponse, RecurringUpdate
from app.services.detection import run_detection
from app.services import analytics

router = APIRouter(prefix="/api/recurring", tags=["recurring"])

UPCOMING_DAYS = 14


def _view(s: RecurringSeries) -> RecurringSeriesResponse:
    return RecurringSeriesResponse(**analytics.series_view(s))


@router.get("", response_model=RecurringOverview)
def list_recurring(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    overview = analytics.recurring_overview(db, current_user.id)
    return RecurringOverview(
        series=overview["series"], monthly_committed=overview["monthly_committed"],
        upcoming=analytics.upcoming(db, current_user.id, UPCOMING_DAYS),
    )


@router.patch("/{series_id}", response_model=RecurringSeriesResponse)
def update_recurring(
    series_id: uuid.UUID,
    payload: RecurringUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    s = db.query(RecurringSeries).filter(RecurringSeries.id == series_id, RecurringSeries.user_id == current_user.id).first()
    if s is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring series not found.")
    fields = {"user_status": "user_status", "name": "user_name", "type": "user_type", "usage": "usage"}
    for field in payload.model_fields_set:
        setattr(s, fields[field], getattr(payload, field))
    db.commit()
    db.refresh(s)
    return _view(s)


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
def refresh(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run_detection(db, current_user)
