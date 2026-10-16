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
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.correction import Correction
from app.models.transaction import Transaction, TransactionKind, TransactionSource, TransactionNature, KIND_DIRECTIONS
from app.models.transaction_source import StatementSourceType, TransactionDirection, TransactionSourceRecord
from app.models.user import User
from app.schemas.transaction import (
    ManualTransactionCreate,
    TransactionUpdate,
    TransactionListResponse,
    TransactionResponse,
    MonthlySummary,
    CategorySummary,
)
from app.schemas.imports import ImportRow, ImportBatchResult
from app.services.merchant_normalizer import normalize
from app.core import clock
from app.services import analytics
from app.services.dedup_matcher import ingest_or_match_transaction
from app.services.detection import run_detection
from app.services.keys import merchant_key, merchants_containing
from app.services.rules import learn_from

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

_CATEGORY_SENT_TO_PEOPLE = "Sent to People"
_CATEGORY_RECEIVED_FROM_PEOPLE = "Received from People"



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
    batch_txn_ids: set = set()

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
            txn, source_record, was_matched = ingest_or_match_transaction(
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
                source_label=row.source_label,
            )
        except Exception as e:
            db.rollback()
            result.failed += 1
            logger.error(f"import_rows: user={user.id} row failed ({e.__class__.__name__}: {e})")
            continue

        if txn is not None:
            batch_txn_ids.add(txn.id)
        if was_matched:
            result.duplicates_merged += 1
        else:
            result.imported += 1
            if category is None:
                result.rows_needing_review += 1

    ctx = run_detection(db, user)
    result.transfers_flagged = sum(1 for t in ctx.txns if t.id in batch_txn_ids and t.kind == TransactionKind.transfer)
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
    run_detection(db, user)
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


def update_transaction(db: Session, txn: Transaction, payload: TransactionUpdate) -> tuple[Transaction, Optional[dict]]:
    """
    Apply the user's edits, learn a rule if the edit makes one, re-run
    detection. Returns (transaction, rule_applied) where rule_applied
    describes a newly learned rule and how many other transactions it changed.
    """
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
    db.flush()  # the session doesn't autoflush; learning reads these corrections

    rule = None
    for field in ("category", "kind"):
        if field in payload.model_fields_set:
            rule = learn_from(db, txn, field) or rule
    db.commit()
    before = {}
    if rule:
        before = {t.id: getattr(t, rule.field) for t in db.query(Transaction).filter(Transaction.user_id == txn.user_id)
                  if merchant_key(t) == rule.merchant_key and t.id != txn.id}
    run_detection(db, txn.user)
    db.refresh(txn)
    if not rule:
        return txn, None
    changed = sum(1 for t in db.query(Transaction).filter(Transaction.id.in_(list(before))) if getattr(t, rule.field) != before[t.id])
    return txn, {"rule_id": rule.id, "merchant": rule.merchant_label, "field": rule.field,
                 "value": rule.value, "applied_count": changed}


class SplitError(ValueError):
    pass


def split_transaction(db: Session, txn: Transaction, parts) -> Transaction:
    """Replace txn in totals by 2+ parts that sum to it exactly."""
    if txn.split_parent_id is not None:
        raise SplitError("A split part can't be split again.")
    if txn.is_split:
        raise SplitError("Already split. Unsplit it first.")
    if txn.kind not in (TransactionKind.spend, TransactionKind.income):
        raise SplitError("Only spending or income can be split.")
    total = sum((Decimal(p.amount) for p in parts), Decimal("0"))
    if total != txn.amount:
        raise SplitError(f"Parts add up to ₹{total}, but the transaction is ₹{txn.amount}.")
    for i, part in enumerate(parts):
        db.add(Transaction(
            user_id=txn.user_id, source=txn.source, merchant_raw=txn.merchant_raw, merchant_clean=txn.merchant_clean,
            category=part.category, auto_category=part.category, transaction_nature=txn.transaction_nature,
            direction=txn.direction, kind=txn.kind, amount=Decimal(part.amount), currency=txn.currency,
            transaction_date=txn.transaction_date, split_parent_id=txn.id,
            idempotency_key=hashlib.sha256(f"split|{txn.id}|{i}".encode()).hexdigest(),
        ))
    txn.is_split = True
    db.commit()
    db.refresh(txn)
    return txn


def unsplit_transaction(db: Session, txn: Transaction) -> Transaction:
    if not txn.is_split:
        raise SplitError("This transaction isn't split.")
    for part in list(txn.splits):
        db.delete(part)
    txn.is_split = False
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
    user = txn.user
    db.query(TransactionSourceRecord).filter(TransactionSourceRecord.transaction_id == txn.id).delete()
    db.delete(txn)
    db.commit()
    run_detection(db, user)


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
    person_id: Optional[uuid.UUID] = None,
) -> TransactionListResponse:
    # Split parts are listed under their parent (TransactionResponse.splits)
    query = db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.split_parent_id.is_(None))

    if category:
        query = query.filter(Transaction.category == category)
    if merchant:
        query = query.filter(Transaction.merchant_clean.in_(merchants_containing(db, user.id, merchant)))
    if source:
        query = query.filter(Transaction.source == source)
    if date_from:
        query = query.filter(Transaction.transaction_date >= date_from)
    if date_to:
        query = query.filter(Transaction.transaction_date <= date_to)
    if person_id:
        query = query.filter(Transaction.person_id == person_id)

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
# Dashboard summary — a view over services/analytics.py
# ─────────────────────────────────────────────

def _floor(period_start: date, date_floor: Optional[datetime]) -> date:
    return max(period_start, date_floor.date()) if date_floor else period_start


def _categories(db, user_id, start: date, end: date, prev: Optional[tuple[date, date]] = None,
                budgets: Optional[dict] = None) -> tuple[list[CategorySummary], dict]:
    spend = analytics.spend_summary(db, user_id, start, end, "category")
    prev_by = {g["key"]: g["total"] for g in analytics.spend_summary(db, user_id, *prev, "category")["groups"]} if prev else {}
    total = spend["total"]
    out = []
    for g in spend["groups"]:
        limit = budgets.get(g["key"]) if budgets else None
        prev_total = prev_by.get(g["key"], analytics.ZERO)
        mom = (g["total"] - prev_total) if prev else None
        out.append(CategorySummary(
            category=g["label"], total=g["total"], transaction_count=g["count"],
            percentage_of_spend=(g["total"] / total * 100).quantize(Decimal("0.1")) if total > 0 else Decimal("0.0"),
            budget_limit=limit,
            budget_consumed_pct=(g["total"] / limit * 100).quantize(Decimal("0.1")) if limit else None,
            mom_delta=mom,
            mom_delta_pct=((mom / prev_total) * 100).quantize(Decimal("0.1")) if prev and prev_total > 0 else None,
        ))
    return out, spend


def _top_merchants(db, user_id, start: date, end: date) -> list[dict]:
    return [{"merchant_clean": None if g["key"] is None else g["label"], "total": float(g["total"]), "count": g["count"]}
            for g in analytics.top_merchants(db, user_id, start, end, 10)]


def get_monthly_summary(
    db: Session,
    user: User,
    year: int,
    month: int,
    date_floor: Optional[datetime] = None,
) -> MonthlySummary:
    """date_floor: earliest visible date (free tier). Data before it is excluded."""
    first, last = analytics.month_bounds(date(year, month, 1))
    start = _floor(first, date_floor)
    prev_first, prev_last = analytics.month_bounds(first - timedelta(days=1))
    show_mom = not (date_floor and prev_first < date_floor.date())   # previous month outside the free window

    budgets = analytics.active_budgets(db, user.id)
    categories, spend = _categories(db, user.id, start, last, (prev_first, prev_last) if show_mom else None, budgets)
    income = analytics.income_summary(db, user.id, start, last)["total"]
    prev_total = analytics.spend_summary(db, user.id, prev_first, prev_last)["total"] if show_mom else None

    today = clock.today()
    days_remaining = (last - today).days if first <= today <= last else (last.day if first > today else 0)
    lo, hi = analytics.bounds(start, last)
    return MonthlySummary(
        period_start=lo, period_end=hi, period="month",
        total_spend=spend["total"], total_received=income, net_cash_flow=income - spend["total"],
        transaction_count=spend["count"], total_budget=budgets.get(None), days_remaining=days_remaining,
        categories=categories, top_merchants=_top_merchants(db, user.id, start, last),
        mom_total_delta=(spend["total"] - prev_total) if show_mom else None,
        mom_total_delta_pct=((spend["total"] - prev_total) / prev_total * 100).quantize(Decimal("0.1"))
        if show_mom and prev_total > 0 else None,
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
    today = clock.today()
    if period == "year":
        target_year = year or today.year
        start, end = date(target_year, 1, 1), date(target_year, 12, 31)
        months_elapsed = today.month if target_year == today.year else 12
    else:  # lifetime
        start, end = date(2000, 1, 1), date(2100, 12, 31)
        earliest = db.query(func.min(Transaction.transaction_date)).filter(Transaction.user_id == user.id).scalar()
        earliest = max(earliest.date(), date_floor.date()) if earliest and date_floor else (earliest.date() if earliest else None)
        months_elapsed = max((today.year - earliest.year) * 12 + (today.month - earliest.month), 1) if earliest else 1
    if date_floor and start < date_floor.date():
        start, months_elapsed = date_floor.date(), 1

    categories, spend = _categories(db, user.id, start, end)
    income = analytics.income_summary(db, user.id, start, end)["total"]
    lo, hi = analytics.bounds(start, end)
    return MonthlySummary(
        period_start=lo, period_end=hi, period=period,
        total_spend=spend["total"], total_received=income, net_cash_flow=income - spend["total"],
        transaction_count=spend["count"], avg_monthly_spend=(spend["total"] / months_elapsed).quantize(Decimal("0.01")),
        categories=categories, top_merchants=_top_merchants(db, user.id, start, end),
    )
