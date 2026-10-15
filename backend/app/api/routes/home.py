"""
Home screen: every card's numbers in one call, all from services/analytics.py.

  GET /api/home?month=YYYY-MM   (default: this month; past months for history)
"""

import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core import clock
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.anomaly import Anomaly
from app.models.user import User
from app.schemas.review import ReviewCardResponse
from app.services import analytics, cash, coverage
from app.services.review import build_cards

router = APIRouter(prefix="/api/home", tags=["home"])

UPCOMING_DAYS = 14
ATTENTION_CARDS = 2


@router.get("")
def home(month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
         current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = clock.today()
    try:
        first = date.fromisoformat(f"{month}-01") if month else today.replace(day=1)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="month must look like 2024-06")
    current = first == today.replace(day=1)
    cards = build_cards(db, current_user)
    data = {
        "month": first.isoformat()[:7],
        "is_current_month": current,
        "safe_to_spend": analytics.safe_to_spend_today(db, current_user.id) if current else None,
        "outlook": analytics.month_outlook(db, current_user.id, first),
        "budgets": analytics.budget_status(db, current_user.id, first),
        "upcoming": analytics.upcoming(db, current_user.id, UPCOMING_DAYS) if current else [],
        "attention": {
            "review_count": len(cards),
            "review_cards": [ReviewCardResponse.model_validate(c, from_attributes=True).model_dump() for c in cards[:ATTENTION_CARDS]],
            "anomaly_count": db.query(Anomaly).filter(Anomaly.user_id == current_user.id, Anomaly.status == "open").count(),
        },
        "coverage": coverage.sources(db, current_user),
        "cash_balance": cash.wallet(db, current_user.id)["balance"],
    }
    return json.loads(json.dumps(data, default=str))   # Decimals as strings, like every other route
