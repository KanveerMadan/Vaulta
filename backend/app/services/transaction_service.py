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

from app.models.transaction import Transaction, Budget, TransactionSource, TransactionNature
from app.models.transaction_source import StatementSourceType, TransactionDirection
from app.models.user import User
from app.schemas.transaction import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    MonthlySummary,
    CategorySummary,
)
from app.services.csv_parser import parse_csv, CSVParseError, DetectedBank
from app.services.upi_statement_parser import (
    parse_upi_statement,
    UPIParseError,
    UPISource,
    RawUPITransaction,
)
from app.services.merchant_normalizer import normalize
from app.services.dedup_matcher import ingest_or_match_transaction

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

_CATEGORY_SENT_TO_PEOPLE = "Sent to People"
_CATEGORY_RECEIVED_FROM_PEOPLE = "Received from People"

_UPI_SOURCE_MAP: dict[UPISource, StatementSourceType] = {
    UPISource.GOOGLE_PAY: StatementSourceType.upi_google_pay,
    UPISource.PHONEPE: StatementSourceType.upi_phonepe,
    UPISource.PAYTM: StatementSourceType.upi_paytm,
}

_SPEND_NATURES = (TransactionNature.expense, TransactionNature.peer_payment_sent)
_INCOME_NATURES = (TransactionNature.income, TransactionNature.peer_payment_received)


def _nature_from_upi_direction(direction: str, merchant_clean: Optional[str]) -> TransactionNature:
    if direction == "self_transfer":
        return TransactionNature.self_transfer
    if direction == "paid":
        return TransactionNature.expense if merchant_clean else TransactionNature.peer_payment_sent
    if direction == "received":
        return TransactionNature.income if merchant_clean else TransactionNature.peer_payment_received
    logger.warning(f"Unknown UPI direction string '{direction}' — defaulting to expense")
    return TransactionNature.expense


def _category_from_nature(nature: TransactionNature, normalizer_category: Optional[str]) -> Optional[str]:
    if nature == TransactionNature.peer_payment_sent:
        return _CATEGORY_SENT_TO_PEOPLE
    if nature == TransactionNature.peer_payment_received:
        return _CATEGORY_RECEIVED_FROM_PEOPLE
    return normalizer_category


def _direction_from_upi_string(direction: str) -> TransactionDirection:
    if direction == "received":
        return TransactionDirection.credit
    return TransactionDirection.debit


# ─────────────────────────────────────────────
# Ingestion
# ─────────────────────────────────────────────

def ingest_csv(
    db: Session,
    user: User,
    file_bytes: bytes,
    filename: str,
) -> dict:
    bank, raw_transactions = parse_csv(file_bytes, filename=filename)

    inserted = 0
    matched_existing = 0
    skipped_duplicate = 0

    for raw_txn in raw_transactions:
        normalized = normalize(raw_txn.merchant_raw)
        merchant_clean = normalized.merchant_clean if normalized.confidence >= 0.5 else None
        category = normalized.category if normalized.confidence >= 0.5 else None

        try:
            txn, source_record, was_matched = ingest_or_match_transaction(
                db,
                user,
                source=StatementSourceType.bank_csv,
                direction=TransactionDirection.debit,
                amount=raw_txn.amount,
                transaction_date_hint=raw_txn.transaction_date,
                idempotency_key=raw_txn.idempotency_key,
                merchant_raw=raw_txn.merchant_raw,
                merchant_clean=merchant_clean,
                category=category,
                transaction_nature=TransactionNature.expense,
                legacy_source_enum=TransactionSource.csv,
                utr=None,
                vpa=None,
                raw_timestamp=None,
                raw_date=raw_txn.transaction_date.date(),
                counterparty_raw=raw_txn.merchant_raw,
                currency="INR",
                raw_row=raw_txn.raw_row,
            )

            if source_record.match_tier is not None:
                matched_existing += 1
            elif was_matched:
                skipped_duplicate += 1
            else:
                inserted += 1

        except Exception as e:
            logger.error(
                f"ingest_csv: unexpected error on row idempotency_key="
                f"{raw_txn.idempotency_key!r}: {e} — skipping"
            )

    logger.info(
        f"CSV ingest complete: user={user.id}, bank={bank.value}, "
        f"total_rows={len(raw_transactions)}, inserted={inserted}, "
        f"matched_existing={matched_existing}, skipped_duplicate={skipped_duplicate}"
    )

    return {
        "bank": bank.value,
        "total_rows": len(raw_transactions),
        "inserted": inserted,
        "matched_existing": matched_existing,
        "skipped_duplicate": skipped_duplicate,
    }


def ingest_upi_statement(
    db: Session,
    user: User,
    file_bytes: bytes,
    filename: str,
) -> dict:
    upi_source, raw_transactions = parse_upi_statement(file_bytes, filename=filename)

    statement_source = _UPI_SOURCE_MAP.get(upi_source)
    if statement_source is None:
        raise UPIParseError(f"No StatementSourceType mapping for UPISource.{upi_source.value}")

    inserted = 0
    matched_existing = 0
    skipped_duplicate = 0
    by_nature: dict[str, int] = {}

    for raw_txn in raw_transactions:
        normalized = normalize(raw_txn.merchant_raw_unspaced)
        merchant_clean = normalized.merchant_clean if normalized.confidence >= 0.5 else None
        normalizer_category = normalized.category if normalized.confidence >= 0.5 else None

        nature = _nature_from_upi_direction(raw_txn.direction, merchant_clean)
        category = _category_from_nature(nature, normalizer_category)
        direction = _direction_from_upi_string(raw_txn.direction)

        by_nature[nature.value] = by_nature.get(nature.value, 0) + 1

        try:
            txn, source_record, was_matched = ingest_or_match_transaction(
                db,
                user,
                source=statement_source,
                direction=direction,
                amount=raw_txn.amount,
                transaction_date_hint=raw_txn.transaction_date,
                idempotency_key=raw_txn.idempotency_key,
                merchant_raw=raw_txn.merchant_raw,
                merchant_clean=merchant_clean,
                category=category,
                transaction_nature=nature,
                legacy_source_enum=TransactionSource.csv,
                utr=raw_txn.utr,
                vpa=None,
                raw_timestamp=raw_txn.transaction_date,
                raw_date=raw_txn.transaction_date.date(),
                counterparty_raw=raw_txn.merchant_raw_unspaced,
                currency="INR",
                raw_row=raw_txn.raw_row,
            )

            if source_record.match_tier is not None:
                matched_existing += 1
            elif was_matched:
                skipped_duplicate += 1
            else:
                inserted += 1

        except Exception as e:
            logger.error(
                f"ingest_upi_statement: unexpected error on UTR={raw_txn.utr!r}: {e} — skipping"
            )

    logger.info(
        f"UPI statement ingest complete: user={user.id}, source={upi_source.value}, "
        f"total_rows={len(raw_transactions)}, inserted={inserted}, "
        f"matched_existing={matched_existing}, skipped_duplicate={skipped_duplicate}, "
        f"by_nature={by_nature}"
    )

    return {
        "source": upi_source.value,
        "total_rows": len(raw_transactions),
        "inserted": inserted,
        "matched_existing": matched_existing,
        "skipped_duplicate": skipped_duplicate,
        "by_nature": by_nature,
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
    query = db.query(Transaction).filter(Transaction.user_id == user.id)

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
# Summary helpers
# ─────────────────────────────────────────────

def _get_active_budgets(db: Session, user_id: uuid.UUID) -> dict:
    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == user_id, Budget.is_active == "true")
        .all()
    )
    return {b.category: b.monthly_limit for b in budgets}


def _build_spend_rows(db, user_id, period_start, period_end):
    return (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.transaction_nature.in_(_SPEND_NATURES),
        )
        .group_by(Transaction.category)
        .all()
    )


def _build_top_merchants(db, user_id, period_start, period_end):
    rows = (
        db.query(
            Transaction.merchant_clean,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.transaction_nature.in_(_SPEND_NATURES),
        )
        .group_by(Transaction.merchant_clean)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(10)
        .all()
    )
    return [
        {"merchant_clean": r.merchant_clean, "total": float(r.total or 0), "count": r.count}
        for r in rows
    ]


def _get_total_received(db, user_id, period_start, period_end) -> Decimal:
    result = (
        db.query(func.sum(Transaction.amount).label("total"))
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.transaction_nature.in_(_INCOME_NATURES),
        )
        .first()
    )
    return result.total if result and result.total else Decimal("0")


# ─────────────────────────────────────────────
# Summary computation
# ─────────────────────────────────────────────

def get_monthly_summary(
    db: Session,
    user: User,
    year: int,
    month: int,
) -> MonthlySummary:
    _, last_day = monthrange(year, month)
    period_start = datetime(year, month, 1, tzinfo=timezone.utc)
    period_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    _, prev_last_day = monthrange(prev_year, prev_month)
    prev_start = datetime(prev_year, prev_month, 1, tzinfo=timezone.utc)
    prev_end = datetime(prev_year, prev_month, prev_last_day, 23, 59, 59, tzinfo=timezone.utc)

    today = datetime.now(timezone.utc)
    if year == today.year and month == today.month:
        days_remaining = last_day - today.day
    elif datetime(year, month, 1, tzinfo=timezone.utc) > today:
        days_remaining = last_day
    else:
        days_remaining = 0

    spend_rows = _build_spend_rows(db, user.id, period_start, period_end)
    total_spend = sum(row.total for row in spend_rows if row.total) or Decimal("0")
    total_spend_count = sum(row.count for row in spend_rows)
    total_received = _get_total_received(db, user.id, period_start, period_end)
    net_cash_flow = total_received - total_spend

    prev_rows = _build_spend_rows(db, user.id, prev_start, prev_end)
    prev_by_category = {row.category: row.total for row in prev_rows}
    prev_total = sum(prev_by_category.values()) or Decimal("0")

    budgets = _get_active_budgets(db, user.id)
    total_budget: Optional[Decimal] = budgets.get(None)

    categories: List[CategorySummary] = []
    for row in sorted(spend_rows, key=lambda r: -(r.total or 0)):
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

    top_merchants = _build_top_merchants(db, user.id, period_start, period_end)

    mom_total_delta = (total_spend - prev_total).quantize(Decimal("0.01"))
    mom_total_delta_pct = None
    if prev_total > 0:
        mom_total_delta_pct = ((mom_total_delta / prev_total) * 100).quantize(Decimal("0.1"))

    return MonthlySummary(
        period_start=period_start,
        period_end=period_end,
        period="month",
        total_spend=total_spend.quantize(Decimal("0.01")),
        total_received=total_received.quantize(Decimal("0.01")),
        net_cash_flow=net_cash_flow.quantize(Decimal("0.01")),
        transaction_count=total_spend_count,
        total_budget=total_budget,
        days_remaining=days_remaining,
        categories=categories,
        top_merchants=top_merchants,
        mom_total_delta=mom_total_delta,
        mom_total_delta_pct=mom_total_delta_pct,
    )


def get_period_summary(
    db: Session,
    user: User,
    period: str,
    year: Optional[int] = None,
) -> MonthlySummary:
    """
    Year or lifetime summary. No budget tracking, no days_remaining.
    avg_monthly_spend replaces those cards on the frontend.
    """
    today = datetime.now(timezone.utc)

    if period == "year":
        target_year = year or today.year
        period_start = datetime(target_year, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(target_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        months_elapsed = today.month if target_year == today.year else 12
    else:  # lifetime
        period_start = datetime(2000, 1, 1, tzinfo=timezone.utc)
        period_end = datetime(2100, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        earliest = (
            db.query(func.min(Transaction.transaction_date))
            .filter(Transaction.user_id == user.id)
            .scalar()
        )
        if earliest:
            earliest = earliest.replace(tzinfo=timezone.utc) if earliest.tzinfo is None else earliest
            delta_months = (today.year - earliest.year) * 12 + (today.month - earliest.month)
            months_elapsed = max(delta_months, 1)
        else:
            months_elapsed = 1

    spend_rows = _build_spend_rows(db, user.id, period_start, period_end)
    total_spend = sum(row.total for row in spend_rows if row.total) or Decimal("0")
    total_spend_count = sum(row.count for row in spend_rows)
    total_received = _get_total_received(db, user.id, period_start, period_end)
    net_cash_flow = total_received - total_spend
    avg_monthly_spend = (total_spend / months_elapsed).quantize(Decimal("0.01"))

    categories: List[CategorySummary] = []
    for row in sorted(spend_rows, key=lambda r: -(r.total or 0)):
        cat = row.category or "Uncategorized"
        cat_total = row.total or Decimal("0")
        pct_of_spend = (cat_total / total_spend * 100) if total_spend > 0 else Decimal("0")
        categories.append(CategorySummary(
            category=cat,
            total=cat_total.quantize(Decimal("0.01")),
            transaction_count=row.count,
            percentage_of_spend=pct_of_spend.quantize(Decimal("0.1")),
        ))

    top_merchants = _build_top_merchants(db, user.id, period_start, period_end)

    return MonthlySummary(
        period_start=period_start,
        period_end=period_end,
        period=period,
        total_spend=total_spend.quantize(Decimal("0.01")),
        total_received=total_received.quantize(Decimal("0.01")),
        net_cash_flow=net_cash_flow.quantize(Decimal("0.01")),
        transaction_count=total_spend_count,
        avg_monthly_spend=avg_monthly_spend,
        categories=categories,
        top_merchants=top_merchants,
    )