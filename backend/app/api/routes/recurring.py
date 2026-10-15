"""
Recurring payments.

  GET   /api/recurring        series, monthly committed total, next 14 days
  PATCH /api/recurring/{id}   confirm/dismiss, rename, retype, keep/review
  POST  /api/recurring/refresh  re-run detection now
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import clock
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.recurring import RecurringSeries
from app.models.user import User
from app.schemas.recurring import RecurringOverview, RecurringSeriesResponse, RecurringUpdate
from app.services.detection import run_detection
from app.services.recurring import monthly_equivalent

router = APIRouter(prefix="/api/recurring", tags=["recurring"])

UPCOMING_DAYS = 14
_COMMITTED = ("active", "missed")


def _view(s: RecurringSeries) -> RecurringSeriesResponse:
    return RecurringSeriesResponse(
        id=s.id, name=s.user_name or s.display_name, cadence=s.cadence, typical_amount=s.typical_amount,
        monthly_amount=monthly_equivalent(s), last_amount=s.last_amount, last_date=s.last_date,
        next_expected=s.next_expected, occurrences=s.occurrences, status=s.status,
        type=s.user_type or s.type_guess, category=s.category,
        price_change={"old": s.previous_amount, "new": s.typical_amount} if s.previous_amount is not None else None,
        user_status=s.user_status, usage=s.usage,
    )


@router.get("", response_model=RecurringOverview)
def list_recurring(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(RecurringSeries)
        .filter(RecurringSeries.user_id == current_user.id)
        .order_by(RecurringSeries.next_expected)
        .all()
    )
    visible = [s for s in rows if s.user_status != "dismissed"]
    today = clock.today()
    return RecurringOverview(
        series=[_view(s) for s in visible],
        monthly_committed=sum((monthly_equivalent(s) for s in visible if s.status in _COMMITTED), Decimal("0.00")),
        upcoming=[_view(s) for s in visible
                  if s.status in _COMMITTED and today <= s.next_expected <= today + timedelta(days=UPCOMING_DAYS)],
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
