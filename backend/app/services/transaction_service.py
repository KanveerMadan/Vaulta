"""
Transaction Service — Phase 1

All business logic for transaction ingestion, querying, and summary computation.
Routes are thin; this file is where the work happens.
"""

from __future__ import annotations

import logging
import uuid
from calendar import monthrange
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import func, select, and_, extract
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.transaction import Transaction, Budget, TransactionSource
from app.models.user import User
from app.schemas.transaction import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    MonthlySummary,
    CategorySummary,
)
from app.services.csv_parser import parse_csv, CSVParseError, DetectedBank
from app.services.merchant_normalizer import normalize

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Ingestion
# ─────────────────────────────────────────────

def ingest_csv(
    db: Session,
    user: User,
    file_bytes: bytes,
    filename: str,
) -> dict:
    """
    Parse a bank CSV, normalize merchants, and insert transactions.
    Idempotent: re-uploading the same file is safe (duplicate keys are ignored).

    Returns a summary dict: {bank, total_rows, inserted, skipped_duplicate, skipped_parse_error}
    """
    bank, raw_transactions = parse_csv(file_bytes, filename=filename)

    inserted = 0
    skipped_duplicate = 0

    for raw_txn in raw_transactions:
        normalized = normalize(raw_txn.merchant_raw)

        txn = Transaction(
            id=uuid.uuid4(),
            user_id=user.id,
            source=TransactionSource.csv,
            merchant_raw=raw_txn.merchant_raw,
            merchant_clean=normalized.merchant_clean,
            category=normalized.category if normalized.confidence >= 0.5 else None,
            amount=raw_txn.amount,
            currency="INR",
            transaction_date=raw_txn.transaction_date,
            idempotency_key=raw_txn.idempotency_key,
            raw_source_data=raw_txn.raw_row,
        )

        try:
            db.add(txn)
            db.flush()  # Flush individually to catch per-row integrity errors
            inserted += 1
        except IntegrityError:
            db.rollback()
            skipped_duplicate += 1
            logger.debug(f"Duplicate transaction skipped: {raw_txn.idempotency_key}")

    db.commit()

    logger.info(
        f"CSV ingest complete: user={user.id}, bank={bank.value}, "
        f"inserted={inserted}, skipped_duplicate={skipped_duplicate}"
    )

    return {
        "bank": bank.value,
        "total_rows": len(raw_transactions),
        "inserted": inserted,
        "skipped_duplicate": skipped_duplicate,
    }


# ─────────────────────────────────────────────
# Querying
# ─────────────────────────────────────────────

def get_transactions(
    db: Session,
    user: User,
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = None,
    merchant: Optional[str] = None,
    source: Optional[TransactionSource] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> TransactionListResponse:
    """
    Paginated, filterable transaction list for the authenticated user.
    Always scoped to user.id — never returns another user's transactions.
    """
    query = db.query(Transaction).filter(
        Transaction.user_id == user.id
    )

    if category:
        query = query.filter(Transaction.category == category)
    if merchant:
        query = query.filter(Transaction.merchant_clean.ilike(f"%{merchant}%"))
    if source:
        query = query.filter(Transaction.source == source)
    if date_from:
        query = query.filter(Transaction.transaction_date >= date_from)
    if date_to:
        query = query.filter(Transaction.transaction_date <= date_to)

    total = query.count()

    items = (
        query
        .order_by(Transaction.transaction_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return TransactionListResponse(
        items=[TransactionResponse.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


# ─────────────────────────────────────────────
# Summary computation
# ─────────────────────────────────────────────

def _get_active_budgets(db: Session, user_id: uuid.UUID) -> dict:
    """
    Fetch active budgets for user. Returns {category_or_None: Decimal}.
    None key = overall monthly budget.
    """
    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == user_id, Budget.is_active == "true")
        .all()
    )
    return {b.category: b.monthly_limit for b in budgets}


def get_monthly_summary(
    db: Session,
    user: User,
    year: int,
    month: int,
) -> MonthlySummary:
    """
    Compute a full monthly summary for the given user/year/month.
    Includes category breakdown with budget status and MoM deltas.

    This is what Dashboard.jsx MetricCards are wired to.
    """
    # Period bounds
    _, last_day = monthrange(year, month)
    period_start = datetime(year, month, 1, tzinfo=timezone.utc)
    period_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    # Previous month bounds for MoM delta
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    _, prev_last_day = monthrange(prev_year, prev_month)
    prev_start = datetime(prev_year, prev_month, 1, tzinfo=timezone.utc)
    prev_end = datetime(prev_year, prev_month, prev_last_day, 23, 59, 59, tzinfo=timezone.utc)

    # Days remaining in current period
    today = datetime.now(timezone.utc)
    if year == today.year and month == today.month:
        days_remaining = last_day - today.day
    elif datetime(year, month, 1, tzinfo=timezone.utc) > today:
        days_remaining = last_day  # Future month
    else:
        days_remaining = 0  # Past month

    # ── Current month category totals ────────────────────────────────────────
    current_rows = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .filter(
            Transaction.user_id == user.id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
        )
        .group_by(Transaction.category)
        .all()
    )

    total_spend = sum(row.total for row in current_rows if row.total) or Decimal("0")
    total_count = sum(row.count for row in current_rows)

    # ── Previous month totals for MoM ────────────────────────────────────────
    prev_rows = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.user_id == user.id,
            Transaction.transaction_date >= prev_start,
            Transaction.transaction_date <= prev_end,
        )
        .group_by(Transaction.category)
        .all()
    )
    prev_by_category = {row.category: row.total for row in prev_rows}
    prev_total = sum(prev_by_category.values()) or Decimal("0")

    # ── Budgets ───────────────────────────────────────────────────────────────
    budgets = _get_active_budgets(db, user.id)
    total_budget: Optional[Decimal] = budgets.get(None)  # None key = overall budget

    # ── Build category summaries ──────────────────────────────────────────────
    categories: List[CategorySummary] = []
    for row in sorted(current_rows, key=lambda r: -(r.total or 0)):
        cat = row.category or "Uncategorized"
        cat_total = row.total or Decimal("0")
        prev_cat_total = prev_by_category.get(row.category, Decimal("0")) or Decimal("0")
        budget_limit = budgets.get(row.category)

        pct_of_spend = (cat_total / total_spend * 100) if total_spend > 0 else Decimal("0")

        budget_consumed_pct = None
        if budget_limit and budget_limit > 0:
            budget_consumed_pct = (cat_total / budget_limit * 100).quantize(Decimal("0.1"))

        mom_delta = cat_total - prev_cat_total
        mom_delta_pct = None
        if prev_cat_total > 0:
            mom_delta_pct = ((mom_delta / prev_cat_total) * 100).quantize(Decimal("0.1"))

        categories.append(CategorySummary(
            category=cat,
            total=cat_total.quantize(Decimal("0.01")),
            transaction_count=row.count,
            percentage_of_spend=pct_of_spend.quantize(Decimal("0.1")),
            budget_limit=budget_limit,
            budget_consumed_pct=budget_consumed_pct,
            mom_delta=mom_delta.quantize(Decimal("0.01")),
            mom_delta_pct=mom_delta_pct,
        ))

    # ── Top merchants ─────────────────────────────────────────────────────────
    top_merchant_rows = (
        db.query(
            Transaction.merchant_clean,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .filter(
            Transaction.user_id == user.id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
        )
        .group_by(Transaction.merchant_clean)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(10)
        .all()
    )

    top_merchants = [
        {"merchant_clean": r.merchant_clean, "total": float(r.total or 0), "count": r.count}
        for r in top_merchant_rows
    ]

    # ── MoM totals ────────────────────────────────────────────────────────────
    mom_total_delta = (total_spend - prev_total).quantize(Decimal("0.01"))
    mom_total_delta_pct = None
    if prev_total > 0:
        mom_total_delta_pct = ((mom_total_delta / prev_total) * 100).quantize(Decimal("0.1"))

    return MonthlySummary(
        period_start=period_start,
        period_end=period_end,
        total_spend=total_spend.quantize(Decimal("0.01")),
        transaction_count=total_count,
        total_budget=total_budget,
        days_remaining=days_remaining,
        categories=categories,
        top_merchants=top_merchants,
        mom_total_delta=mom_total_delta,
        mom_total_delta_pct=mom_total_delta_pct,
    )