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

# Pseudo-categories for peer payments — visible in the category chart per
# Section 5, never silently folded into "Uncategorized".
_CATEGORY_SENT_TO_PEOPLE = "Sent to People"
_CATEGORY_RECEIVED_FROM_PEOPLE = "Received from People"

# UPI source → StatementSourceType, used when creating source records.
_UPI_SOURCE_MAP: dict[UPISource, StatementSourceType] = {
    UPISource.GOOGLE_PAY: StatementSourceType.upi_google_pay,
    UPISource.PHONEPE: StatementSourceType.upi_phonepe,
    UPISource.PAYTM: StatementSourceType.upi_paytm,
}


def _nature_from_upi_direction(direction: str, merchant_clean: Optional[str]) -> TransactionNature:
    """
    Derive transaction_nature from the UPI parser's direction string and
    whether the merchant normalizer found a confident match.

    Section 5 classification logic:
    - "self_transfer" → always self_transfer (never counts toward spending or cash flow)
    - "paid" + confident merchant match → expense (real merchant spend)
    - "paid" + no merchant match → peer_payment_sent (money to a person)
    - "received" + confident merchant match → income (e.g. a refund from a merchant)
    - "received" + no merchant match → peer_payment_received (money from a person)
    """
    if direction == "self_transfer":
        return TransactionNature.self_transfer
    if direction == "paid":
        return TransactionNature.expense if merchant_clean else TransactionNature.peer_payment_sent
    if direction == "received":
        return TransactionNature.income if merchant_clean else TransactionNature.peer_payment_received
    # Fallback — shouldn't be reachable with the current parser, but don't crash.
    logger.warning(f"Unknown UPI direction string '{direction}' — defaulting to expense")
    return TransactionNature.expense


def _category_from_nature(nature: TransactionNature, normalizer_category: Optional[str]) -> Optional[str]:
    """
    Determine the category to write to the canonical Transaction.
    Peer-payment natures get their own pseudo-categories so they're visible
    in the category breakdown chart (Section 5), not silently lumped into
    Uncategorized. All other natures use the normalizer's category (which may
    be None if confidence was below threshold).
    """
    if nature == TransactionNature.peer_payment_sent:
        return _CATEGORY_SENT_TO_PEOPLE
    if nature == TransactionNature.peer_payment_received:
        return _CATEGORY_RECEIVED_FROM_PEOPLE
    return normalizer_category


def _direction_from_upi_string(direction: str) -> TransactionDirection:
    if direction == "received":
        return TransactionDirection.credit
    # "paid" and "self_transfer" both represent money leaving the account.
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
    """
    Parse a bank CSV, normalize merchants, and insert transactions via the
    dedup matcher so CSV-origin rows are visible to cross-source matching.

    Idempotent: re-uploading the same file is safe (duplicate idempotency
    keys are ignored at the source-record level by ingest_or_match_transaction).

    Returns a summary dict:
        {bank, total_rows, inserted, matched_existing, skipped_duplicate}
    """
    bank, raw_transactions = parse_csv(file_bytes, filename=filename)

    inserted = 0
    matched_existing = 0
    skipped_duplicate = 0

    for raw_txn in raw_transactions:
        normalized = normalize(raw_txn.merchant_raw)
        merchant_clean = normalized.merchant_clean if normalized.confidence >= 0.5 else None
        category = normalized.category if normalized.confidence >= 0.5 else None

        # CSV parsers skip all credits — every row returned here is a debit.
        # Nature is always expense: bank CSVs show merchant narrations, not
        # peer-payment counterparties or self-transfer labels, so the normalizer
        # confidence gate is the right classification signal.
        # Note: the dedup matcher's tier 4 (date + merchant overlap) is the only
        # tier that can fire for CSV-origin rows — no UTR, no VPA, no timestamp.
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
                # was_matched=True but match_tier=None means duplicate source
                # record (same idempotency key seen before).
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
    """
    Parse a UPI app statement PDF, classify each transaction's nature,
    normalize merchants, and insert via the dedup matcher.

    Self-transfer rows are ingested as canonical transactions (they need to
    exist so the user's transaction feed is complete and auditable) but are
    excluded from all spend and cash-flow totals by get_monthly_summary's
    nature filter. The dedup matcher may match them against bank-statement
    rows for the same movement — that's correct behaviour.

    Returns a summary dict:
        {source, total_rows, inserted, matched_existing, skipped_duplicate,
         by_nature: {nature_value: count}}
    """
    upi_source, raw_transactions = parse_upi_statement(file_bytes, filename=filename)

    statement_source = _UPI_SOURCE_MAP.get(upi_source)
    if statement_source is None:
        # parse_upi_statement raises for UNKNOWN — this guard is for future
        # sources added to UPISource before _UPI_SOURCE_MAP is updated.
        raise UPIParseError(f"No StatementSourceType mapping for UPISource.{upi_source.value}")

    inserted = 0
    matched_existing = 0
    skipped_duplicate = 0
    by_nature: dict[str, int] = {}

    for raw_txn in raw_transactions:
        # Classification: run normalizer on the unspaced raw string, not the
        # display-mangled version — the normalizer's regexes were tuned against
        # narrations that look like "BundlTechnologies", "Zepto", "ZEPTOMARKETPLACE",
        # not against humanized display strings (Section 5 / master prompt).
        normalized = normalize(raw_txn.merchant_raw_unspaced)
        merchant_clean = normalized.merchant_clean if normalized.confidence >= 0.5 else None
        normalizer_category = normalized.category if normalized.confidence >= 0.5 else None

        nature = _nature_from_upi_direction(raw_txn.direction, merchant_clean)
        category = _category_from_nature(nature, normalizer_category)
        direction = _direction_from_upi_string(raw_txn.direction)

        by_nature[nature.value] = by_nature.get(nature.value, 0) + 1

        # For the canonical Transaction's merchant_raw, use the humanized
        # display name (merchant_raw) rather than the unspaced string
        # (merchant_raw_unspaced) — raw_source_data preserves the unspaced
        # original anyway, so nothing is lost.
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
                # TransactionSource.csv is a placeholder — Transaction.source is
                # a stale enum with no UPI value. This is the legacy_source_enum
                # workaround documented in dedup_matcher.py; remove once the two
                # enums are reconciled.
                legacy_source_enum=TransactionSource.csv,
                utr=raw_txn.utr,
                vpa=None,  # Google Pay statements don't expose the VPA
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

# Natures that contribute to Total Spent (money genuinely left the user's
# hand, per Section 5). self_transfer and peer_payment_received never count.
_SPEND_NATURES = (TransactionNature.expense, TransactionNature.peer_payment_sent)

# Natures that count as money-in for net_cash_flow. Does NOT include
# self_transfer (net worth didn't change) or expense/peer_payment_sent.
_INCOME_NATURES = (TransactionNature.income, TransactionNature.peer_payment_received)


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

    transaction_nature aware (Section 5):
    - total_spend: sum of expense + peer_payment_sent rows only
    - total_received: sum of income + peer_payment_received rows
    - net_cash_flow: total_received - total_spend
    - self_transfer rows: excluded from every total
    - Category breakdown: peer_payment_sent/received appear as dedicated
      pseudo-categories ("Sent to People" / "Received from People"), never
      silently folded into Uncategorized.
    """
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

    # ── Current month spend rows (expense + peer_payment_sent) ────────────────
    # self_transfer deliberately excluded by the nature filter.
    spend_rows = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .filter(
            Transaction.user_id == user.id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.transaction_nature.in_(_SPEND_NATURES),
        )
        .group_by(Transaction.category)
        .all()
    )

    total_spend = sum(row.total for row in spend_rows if row.total) or Decimal("0")
    total_spend_count = sum(row.count for row in spend_rows)

    # ── Current month income rows (income + peer_payment_received) ────────────
    income_rows = (
        db.query(
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .filter(
            Transaction.user_id == user.id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.transaction_nature.in_(_INCOME_NATURES),
        )
        .first()
    )

    total_received = (income_rows.total if income_rows and income_rows.total else Decimal("0"))
    net_cash_flow = total_received - total_spend

    # ── Previous month spend totals for MoM ──────────────────────────────────
    prev_rows = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.user_id == user.id,
            Transaction.transaction_date >= prev_start,
            Transaction.transaction_date <= prev_end,
            Transaction.transaction_nature.in_(_SPEND_NATURES),
        )
        .group_by(Transaction.category)
        .all()
    )
    prev_by_category = {row.category: row.total for row in prev_rows}
    prev_total = sum(prev_by_category.values()) or Decimal("0")

    # ── Budgets ───────────────────────────────────────────────────────────────
    budgets = _get_active_budgets(db, user.id)
    total_budget: Optional[Decimal] = budgets.get(None)

    # ── Build category summaries ──────────────────────────────────────────────
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

    # ── Top merchants (spend natures only) ────────────────────────────────────
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
            Transaction.transaction_nature.in_(_SPEND_NATURES),
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

    # ── MoM totals (spend only) ───────────────────────────────────────────────
    mom_total_delta = (total_spend - prev_total).quantize(Decimal("0.01"))
    mom_total_delta_pct = None
    if prev_total > 0:
        mom_total_delta_pct = ((mom_total_delta / prev_total) * 100).quantize(Decimal("0.1"))

    return MonthlySummary(
        period_start=period_start,
        period_end=period_end,
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