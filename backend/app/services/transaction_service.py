"""
Transaction Service — Phase 1

All business logic for transaction ingestion, querying, and summary computation.
Routes are thin; this file is where the work happens.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from calendar import monthrange
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import case, func, select, and_, extract
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.correction import Correction
from app.models.transaction import Transaction, Budget, TransactionKind, TransactionSource, TransactionNature, KIND_DIRECTIONS
from app.models.transaction_source import StatementSourceType, TransactionDirection, TransactionSourceRecord
from app.models.user import User
from app.schemas.transaction import (
    ManualTransactionCreate,
    TransactionUpdate,
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    MonthlySummary,
    CategorySummary,
)
from app.schemas.imports import ImportRow, ImportBatchResult
from app.services.merchant_normalizer import normalize
from app.services.dedup_matcher import ingest_or_match_transaction

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

_CATEGORY_SENT_TO_PEOPLE = "Sent to People"
_CATEGORY_RECEIVED_FROM_PEOPLE = "Received from People"

# Spending is kind=spend net of kind=refund; income is kind=income. Transfers,
# reversals, lent/borrowed/repayment never count. Every summary figure below
# goes through these three expressions.
_NET_SPEND = case(
    (Transaction.kind == TransactionKind.spend, Transaction.amount),
    (Transaction.kind == TransactionKind.refund, -Transaction.amount),
    else_=0,
)
_SPEND_COUNT = case((Transaction.kind == TransactionKind.spend, 1))
_SPEND_KINDS = (TransactionKind.spend, TransactionKind.refund)


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


# ─────────────────────────────────────────────
# Ingestion (rows parsed and sanitized in the browser)
# ─────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))

_UPI_KEY_NAMES = {
    "upi_google_pay": "google_pay",
    "upi_phonepe": "phonepe",
    "upi_paytm": "paytm",
}


def _row_idempotency_key(row: ImportRow, occurrence: int) -> str:
    """
    UPI rows with a reference keep the key the server-side Google Pay parser
    used (upi|google_pay|<utr>), so statements imported before the move to
    browser parsing are recognized. Other rows hash their content; `occurrence`
    separates genuinely identical rows (two ₹20 chais on one day) within a batch.
    """
    if row.source_type in _UPI_KEY_NAMES and row.reference:
        payload = f"upi|{_UPI_KEY_NAMES[row.source_type]}|{row.reference}"
    else:
        payload = "|".join([
            "row", row.source_type, row.date, row.direction, row.amount,
            row.description_raw, row.reference or "", str(occurrence),
        ])
    return hashlib.sha256(payload.encode()).hexdigest()


def _row_nature(row: ImportRow, merchant_clean: Optional[str]) -> TransactionNature:
    if row.type == "transfer":
        return TransactionNature.self_transfer
    if row.source_type in _UPI_KEY_NAMES:
        # UPI apps: an unrecognized counterparty is a person (as before)
        return _nature_from_upi_direction("paid" if row.direction == "debit" else "received", merchant_clean)
    return TransactionNature.expense if row.direction == "debit" else TransactionNature.income


def import_rows(db: Session, user: User, rows: List[ImportRow]) -> ImportBatchResult:
    result = ImportBatchResult()
    seen: dict[tuple, int] = {}

    for row in rows:
        identity = (row.source_type, row.date, row.direction, row.amount, row.description_raw, row.reference)
        occurrence = seen.get(identity, 0)
        seen[identity] = occurrence + 1

        is_upi = row.source_type in _UPI_KEY_NAMES
        # UPI counterparties were normalized with spaces removed; keep that
        normalized = normalize(row.description_raw.replace(" ", "") if is_upi else row.description_raw)
        confident = normalized.confidence >= 0.5
        merchant_clean = normalized.merchant_clean if confident else None
        nature = _row_nature(row, merchant_clean)
        category = _category_from_nature(nature, normalized.category if confident else None)

        if "T" in row.date:
            raw_timestamp = datetime.fromisoformat(row.date).replace(tzinfo=IST)
            raw_date = raw_timestamp.date()
        else:
            raw_timestamp = None
            raw_date = date.fromisoformat(row.date)

        try:
            _txn, source_record, was_matched = ingest_or_match_transaction(
                db,
                user,
                source=StatementSourceType(row.source_type),
                direction=TransactionDirection(row.direction),
                amount=Decimal(row.amount),
                transaction_date_hint=None,
                idempotency_key=_row_idempotency_key(row, occurrence),
                merchant_raw=row.description_raw,
                merchant_clean=merchant_clean,
                category=category,
                transaction_nature=nature,
                kind=TransactionKind.transfer if row.type == "transfer" else None,
                legacy_source_enum=TransactionSource.csv,
                utr=row.reference if row.reference and re.fullmatch(r"\d{12}", row.reference) else None,
                vpa=None,
                raw_timestamp=raw_timestamp,
                raw_date=raw_date,
                counterparty_raw=row.description_raw,
                currency="INR",
                raw_row=row.model_dump(),
            )
        except Exception as e:
            db.rollback()
            result.failed += 1
            logger.error(f"import_rows: user={user.id} row failed ({e.__class__.__name__}: {e})")
            continue

        if nature == TransactionNature.self_transfer:
            result.transfers_flagged += 1
        if was_matched:
            result.duplicates_merged += 1
        else:
            result.imported += 1
            if category is None:
                result.rows_needing_review += 1

    logger.info(f"Import batch: user={user.id}, rows={len(rows)}, result={result.model_dump()}")
    return result


# ─────────────────────────────────────────────
# Manual entry and edits
# ─────────────────────────────────────────────

def create_manual_transaction(db: Session, user: User, payload: ManualTransactionCreate) -> Transaction:
    """
    Manual entries go through the normalizer and the dedup matcher like
    imported rows, so a cash entry later seen in a statement isn't doubled.
    Returns the canonical transaction (the existing one if it matched).
    """
    normalized = normalize(payload.merchant)
    confident = normalized.confidence >= 0.5
    nature = TransactionNature.expense if payload.direction == "debit" else TransactionNature.income
    txn, _record, _matched = ingest_or_match_transaction(
        db,
        user,
        source=StatementSourceType.manual,
        direction=TransactionDirection(payload.direction),
        amount=Decimal(payload.amount),
        transaction_date_hint=None,
        idempotency_key=hashlib.sha256(f"manual|{payload.client_id.lower()}".encode()).hexdigest(),
        merchant_raw=payload.merchant,
        merchant_clean=normalized.merchant_clean if confident else payload.merchant,
        category=payload.category or (normalized.category if confident else None),
        transaction_nature=nature,
        legacy_source_enum=TransactionSource.manual,
        raw_date=date.fromisoformat(payload.date),
        counterparty_raw=payload.merchant,
        raw_row={"entry": "manual", "payment_method": payload.payment_method},
    )
    if payload.notes and txn.notes is None:
        txn.notes = payload.notes
        db.commit()
    db.refresh(txn)
    return txn


def get_owned_transaction(db: Session, user: User, transaction_id: uuid.UUID) -> Optional[Transaction]:
    """The transaction if it belongs to `user`, else None (callers return 404 either way)."""
    return (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.user_id == user.id)
        .first()
    )


class KindDirectionMismatch(ValueError):
    pass


def record_correction(db: Session, txn: Transaction, field: str, new_value: Optional[str]) -> None:
    """Change a field as the user, keeping the before/after. Caller commits."""
    old_value = getattr(txn, field)
    old_value = old_value.value if hasattr(old_value, "value") else old_value
    db.add(Correction(user_id=txn.user_id, transaction_id=txn.id, field=field,
                      old_value=old_value, new_value=new_value))
    setattr(txn, field, TransactionKind(new_value) if field == "kind" else new_value)
    txn.user_corrected = "true"


def update_transaction(db: Session, txn: Transaction, payload: TransactionUpdate) -> Transaction:
    if "kind" in payload.model_fields_set:
        if txn.direction.value not in KIND_DIRECTIONS[TransactionKind(payload.kind)]:
            raise KindDirectionMismatch(
                f"A {txn.direction.value} can't be '{payload.kind}'. "
                f"Allowed: {', '.join(k.value for k, d in KIND_DIRECTIONS.items() if txn.direction.value in d)}."
            )
        record_correction(db, txn, "kind", payload.kind)
    if "category" in payload.model_fields_set:
        record_correction(db, txn, "category", payload.category)
    if "notes" in payload.model_fields_set:
        txn.notes = payload.notes
    db.commit()
    db.refresh(txn)
    return txn


def is_manual_only(txn: Transaction) -> bool:
    """Created by hand and never merged with statement evidence."""
    return txn.source == TransactionSource.manual and all(
        r.source == StatementSourceType.manual for r in txn.source_records
    )


def delete_manual_transaction(db: Session, txn: Transaction) -> None:
    # Its evidence rows go too, so nothing is left pointing at a deleted entry
    db.query(TransactionSourceRecord).filter(TransactionSourceRecord.transaction_id == txn.id).delete()
    db.delete(txn)
    db.commit()


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


def _counted(user_id, period_start, period_end):
    """Filters for rows that can affect totals in a period."""
    return (
        Transaction.user_id == user_id,
        Transaction.transaction_date >= period_start,
        Transaction.transaction_date <= period_end,
    )


def _build_spend_rows(db, user_id, period_start, period_end):
    return (
        db.query(
            Transaction.category,
            func.sum(_NET_SPEND).label("total"),
            func.count(_SPEND_COUNT).label("count"),
        )
        .filter(*_counted(user_id, period_start, period_end), Transaction.kind.in_(_SPEND_KINDS))
        .group_by(Transaction.category)
        .all()
    )


def _build_top_merchants(db, user_id, period_start, period_end):
    rows = (
        db.query(
            Transaction.merchant_clean,
            func.sum(_NET_SPEND).label("total"),
            func.count(_SPEND_COUNT).label("count"),
        )
        .filter(*_counted(user_id, period_start, period_end), Transaction.kind.in_(_SPEND_KINDS))
        .group_by(Transaction.merchant_clean)
        .order_by(func.sum(_NET_SPEND).desc())
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
        .filter(*_counted(user_id, period_start, period_end), Transaction.kind == TransactionKind.income)
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
    date_floor: Optional[datetime] = None,
) -> MonthlySummary:
    """date_floor: earliest visible date (free tier). Data before it is excluded."""
    _, last_day = monthrange(year, month)
    period_start = datetime(year, month, 1, tzinfo=timezone.utc)
    period_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    if date_floor and period_start < date_floor:
        period_start = date_floor

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

    # Previous month is outside the free-tier window — no MoM comparison then.
    show_mom = not (date_floor and prev_start < date_floor)
    prev_rows = _build_spend_rows(db, user.id, prev_start, prev_end) if show_mom else []
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
        mom_delta = (cat_total - prev_cat_total) if show_mom else None
        mom_delta_pct = None
        if show_mom and prev_cat_total > 0:
            mom_delta_pct = ((mom_delta / prev_cat_total) * 100).quantize(Decimal("0.1"))
        categories.append(CategorySummary(
            category=cat,
            total=cat_total.quantize(Decimal("0.01")),
            transaction_count=row.count,
            percentage_of_spend=pct_of_spend.quantize(Decimal("0.1")),
            budget_limit=budget_limit,
            budget_consumed_pct=budget_consumed_pct,
            mom_delta=mom_delta.quantize(Decimal("0.01")) if mom_delta is not None else None,
            mom_delta_pct=mom_delta_pct,
        ))

    top_merchants = _build_top_merchants(db, user.id, period_start, period_end)

    mom_total_delta = (total_spend - prev_total).quantize(Decimal("0.01")) if show_mom else None
    mom_total_delta_pct = None
    if show_mom and prev_total > 0:
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
    date_floor: Optional[datetime] = None,
) -> MonthlySummary:
    """
    Year or lifetime summary. No budget tracking, no days_remaining.
    avg_monthly_spend replaces those cards on the frontend.
    date_floor: earliest visible date (free tier). Data before it is excluded.
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
        if earliest and date_floor and earliest < date_floor:
            earliest = date_floor
        if earliest:
            earliest = earliest.replace(tzinfo=timezone.utc) if earliest.tzinfo is None else earliest
            delta_months = (today.year - earliest.year) * 12 + (today.month - earliest.month)
            months_elapsed = max(delta_months, 1)
        else:
            months_elapsed = 1

    if date_floor and period_start < date_floor:
        period_start = date_floor
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