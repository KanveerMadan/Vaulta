import uuid
from calendar import monthrange
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.subscription import require_active_subscription, get_data_date_floor
from app.models.transaction import TransactionSource
from app.models.user import User
from app.schemas.transaction import (
    ManualTransactionCreate,
    SplitRequest,
    MonthlySummary,
    TransactionListResponse,
    TransactionPatchResponse,
    TransactionResponse,
    TransactionUpdate,
)
from app.services import transaction_service
from app.services.detection import run_detection

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
    person_id: Optional[uuid.UUID] = Query(default=None),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_active_subscription),
    date_floor: Optional[datetime] = Depends(get_data_date_floor),
    db: Session = Depends(get_db),
):
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
        person_id=person_id,
    )


@router.get("/summary", response_model=MonthlySummary)
def get_summary(
    period: str = Query(default="month", pattern="^(month|year|lifetime)$"),
    year: Optional[int] = Query(default=None, ge=2020, le=2100),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_active_subscription),
    date_floor: Optional[datetime] = Depends(get_data_date_floor),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    target_year = year or now.year
    target_month = month or now.month

    # Free-tier window is enforced before any period-specific handling so that
    # year/lifetime can't be used to read history outside the 30-day window.
    if period == "month":
        _, last_day = monthrange(target_year, target_month)
        period_end = datetime(target_year, target_month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    elif period == "year":
        period_end = datetime(target_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    else:
        period_end = None  # lifetime always overlaps the window; it is clamped below
    if date_floor and period_end and period_end < date_floor:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This period is outside your free tier's 30-day window. "
                   "Subscribe to view your full history.",
        )

    if period in ("year", "lifetime"):
        return transaction_service.get_period_summary(
            db=db,
            user=current_user,
            period=period,
            year=target_year if period == "year" else None,
            date_floor=date_floor,
        )

    return transaction_service.get_monthly_summary(
        db=db,
        user=current_user,
        year=target_year,
        month=target_month,
        date_floor=date_floor,
    )


@router.post("/reanalyze", status_code=status.HTTP_204_NO_CONTENT)
def reanalyze(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """Re-run detection (transfers, refunds, people, rules, recurring) over all of the user's transactions."""
    run_detection(db, current_user)


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: ManualTransactionCreate,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """Manual entry (source=manual). Retrying with the same client_id returns the same transaction."""
    return transaction_service.create_manual_transaction(db, current_user, payload)


def _owned_or_404(db: Session, user: User, transaction_id: uuid.UUID):
    txn = transaction_service.get_owned_transaction(db, user, transaction_id)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    return txn


@router.patch("/{transaction_id}", response_model=TransactionPatchResponse)
def update_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """Change category, kind and/or notes. Marks the transaction user_corrected."""
    txn = _owned_or_404(db, current_user, transaction_id)
    try:
        txn, rule_applied = transaction_service.update_transaction(db, txn, payload)
    except transaction_service.KindDirectionMismatch as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return TransactionPatchResponse(**TransactionResponse.model_validate(txn).model_dump(), rule_applied=rule_applied)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """Manual entries only. Imported transactions are corrected, not deleted."""
    txn = _owned_or_404(db, current_user, transaction_id)
    if not transaction_service.is_manual_only(txn):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only transactions you added manually can be deleted.",
        )
    transaction_service.delete_manual_transaction(db, txn)


@router.post("/{transaction_id}/split", response_model=TransactionResponse)
def split_transaction(
    transaction_id: uuid.UUID,
    payload: SplitRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """Split into 2+ parts (amounts must add up exactly). The parts count in totals instead of the original."""
    txn = _owned_or_404(db, current_user, transaction_id)
    try:
        return transaction_service.split_transaction(db, txn, payload.parts)
    except transaction_service.SplitError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete("/{transaction_id}/split", response_model=TransactionResponse)
def unsplit_transaction(
    transaction_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_active_subscription),
    db: Session = Depends(get_db),
):
    """Remove the parts; the original counts again."""
    txn = _owned_or_404(db, current_user, transaction_id)
    try:
        return transaction_service.unsplit_transaction(db, txn)
    except transaction_service.SplitError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
