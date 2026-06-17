from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.subscription import require_active_subscription, get_data_date_floor
from app.models.transaction import TransactionSource
from app.models.user import User
from app.schemas.transaction import TransactionListResponse, MonthlySummary
from app.services import transaction_service

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=TransactionListResponse)
def list_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    category: Optional[str] = Query(default=None),
    merchant: Optional[str] = Query(default=None),
    source: Optional[TransactionSource] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_active_subscription),
    date_floor: Optional[datetime] = Depends(get_data_date_floor),
    db: Session = Depends(get_db),
):
    """
    Paginated, filterable transaction list for the authenticated user.
    Scoped strictly to current_user — cross-user access is impossible by design.

    Trial/free-tier users (subscription_status != "active") are limited to the
    last 30 days of data — `date_floor` (from get_data_date_floor) is applied
    as a lower bound regardless of the requested `date_from`.
    """
    effective_date_from = date_from
    if date_floor and (date_from is None or date_from < date_floor):
        effective_date_from = date_floor

    return transaction_service.get_transactions(
        db=db,
        user=current_user,
        page=page,
        page_size=page_size,
        category=category,
        merchant=merchant,
        source=source,
        date_from=effective_date_from,
        date_to=date_to,
    )


@router.get("/summary", response_model=MonthlySummary)
def get_summary(
    year: Optional[int] = Query(default=None, ge=2020, le=2100),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_active_subscription),
    date_floor: Optional[datetime] = Depends(get_data_date_floor),
    db: Session = Depends(get_db),
):
    """
    Monthly summary: total spend, category breakdown with budget status,
    MoM deltas, and top merchants. Defaults to current month.

    This is what Dashboard.jsx MetricCards and SpendChart consume.

    Trial/free-tier users cannot request a summary for a month entirely
    before their 30-day data window — returns 402 in that case.
    """
    now = datetime.utcnow()
    target_year = year or now.year
    target_month = month or now.month

    if date_floor:
        from calendar import monthrange
        _, last_day = monthrange(target_year, target_month)
        month_end = datetime(target_year, target_month, last_day, 23, 59, 59, tzinfo=date_floor.tzinfo)
        if month_end < date_floor:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="This period is outside your free tier's 30-day window. "
                       "Subscribe to view your full history.",
            )

    return transaction_service.get_monthly_summary(
        db=db,
        user=current_user,
        year=target_year,
        month=target_month,
    )