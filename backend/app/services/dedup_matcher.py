"""
Cross-source deduplication matcher — Section 4 of the VAULTA master prompt.

Owns the write path for turning a single parsed transaction line (from any
source) into either:
  (a) new evidence merged into an EXISTING canonical Transaction, or
  (b) a brand new canonical Transaction.

Callers (csv ingestion, UPI statement ingestion, manual entry — once each is
wired up) are responsible for merchant normalization (merchant_normalizer.py)
and transaction_nature classification (Section 5) BEFORE calling in here.
This module only matches, merges, and persists — it doesn't know how to read
a CSV row or a UPI PDF line.

NOT YET WIRED UP ANYWHERE. ingest_csv (transaction_service.py) still inserts
Transaction rows directly and does not call this. Until it's retrofitted,
cross-source matching only has UPI-side evidence to work with once
ingest_upi_statement exists and calls this — CSV-origin transactions remain
invisible to the matcher. Retrofitting ingest_csv needs csv_parser.py's
RawTransaction fields verified first (does it expose a UTR buried in
narration? a debit/credit sign?) rather than guessed at here.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, date as date_type, timedelta, timezone
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.transaction import Transaction, TransactionSource, TransactionNature
from app.models.transaction_source import (
    TransactionSourceRecord,
    StatementSourceType,
    TransactionDirection,
)
from app.models.user import User

logger = logging.getLogger(__name__)


# Tunable matching windows — Section 4 describes these qualitatively ("tight",
# "within minutes"); these are first-pass values, worth tuning once real
# multi-source data is available (the master prompt flags this explicitly for
# tier 4, but tiers 2-3 are equally first-guess right now).
TIER2_VPA_WINDOW = timedelta(minutes=2)
TIER3_TIME_WINDOW = timedelta(minutes=10)

_MIN_TOKEN_LEN = 3

# transaction_nature values that represent money leaving the user's hand vs
# arriving in it. Used to infer an existing Transaction's direction, since
# Transaction itself has no explicit direction column. self_transfer is
# treated as debit by convention (it represents the sending leg, per how UPI
# statements phrase "Self transfer to X") — an assumption, not a verified
# rule; revisit if self-transfers start appearing from both sides.
_DEBIT_NATURES = {
    TransactionNature.expense,
    TransactionNature.peer_payment_sent,
    TransactionNature.self_transfer,
}
_CREDIT_NATURES = {
    TransactionNature.income,
    TransactionNature.peer_payment_received,
}


def _infer_transaction_direction(txn: Transaction) -> TransactionDirection:
    if txn.transaction_nature in _CREDIT_NATURES:
        return TransactionDirection.credit
    return TransactionDirection.debit


def _normalize_for_overlap(text: Optional[str]) -> set:
    if not text:
        return set()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return {tok for tok in cleaned.split() if len(tok) >= _MIN_TOKEN_LEN}


def _merchant_overlap(a: Optional[str], b: Optional[str]) -> bool:
    """
    First-pass heuristic: any shared token (length >= 3) between the two
    counterparty/merchant strings. Not fuzzy, not weighted. Section 4 flags
    tier 4 (and by extension this) as needing tuning against real multi-source
    data once available — treat this as a starting point, not a final design.
    """
    tokens_a = _normalize_for_overlap(a)
    tokens_b = _normalize_for_overlap(b)
    if not tokens_a or not tokens_b:
        return False
    return bool(tokens_a & tokens_b)


def _existing_source_record_for_idempotency_key(
    db: Session, user_id: uuid.UUID, idempotency_key: str
) -> Optional[TransactionSourceRecord]:
    return (
        db.query(TransactionSourceRecord)
        .filter(
            TransactionSourceRecord.user_id == user_id,
            TransactionSourceRecord.idempotency_key == idempotency_key,
        )
        .first()
    )


def _try_tier1_utr(db: Session, user_id: uuid.UUID, utr: str, direction: TransactionDirection) -> Optional[Transaction]:
    record = (
        db.query(TransactionSourceRecord)
        .filter(
            TransactionSourceRecord.user_id == user_id,
            TransactionSourceRecord.utr == utr,
            TransactionSourceRecord.direction == direction,
            TransactionSourceRecord.transaction_id.isnot(None),
        )
        .first()
    )
    return record.transaction if record else None


def _try_tier2_vpa(
    db: Session,
    user_id: uuid.UUID,
    vpa: str,
    direction: TransactionDirection,
    amount: Decimal,
    raw_timestamp: Optional[datetime],
) -> Optional[Transaction]:
    if raw_timestamp is None:
        return None

    window_start = raw_timestamp - TIER2_VPA_WINDOW
    window_end = raw_timestamp + TIER2_VPA_WINDOW

    candidates = (
        db.query(TransactionSourceRecord)
        .filter(
            TransactionSourceRecord.user_id == user_id,
            TransactionSourceRecord.vpa == vpa,
            TransactionSourceRecord.direction == direction,
            TransactionSourceRecord.transaction_id.isnot(None),
        )
        .all()
    )
    for record in candidates:
        txn = record.transaction
        if txn is None or txn.amount != amount:
            continue
        if window_start <= txn.transaction_date <= window_end:
            return txn
    return None


def _try_tier3_time_and_merchant(
    db: Session,
    user_id: uuid.UUID,
    direction: TransactionDirection,
    amount: Decimal,
    raw_timestamp: Optional[datetime],
    counterparty_raw: Optional[str],
) -> Optional[Transaction]:
    if raw_timestamp is None:
        return None

    window_start = raw_timestamp - TIER3_TIME_WINDOW
    window_end = raw_timestamp + TIER3_TIME_WINDOW

    candidates = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.amount == amount,
            Transaction.transaction_date >= window_start,
            Transaction.transaction_date <= window_end,
        )
        .all()
    )
    for txn in candidates:
        if _infer_transaction_direction(txn) != direction:
            continue
        if _merchant_overlap(counterparty_raw, txn.merchant_clean or txn.merchant_raw):
            return txn
    return None


def _try_tier4_date_and_merchant(
    db: Session,
    user_id: uuid.UUID,
    direction: TransactionDirection,
    amount: Decimal,
    raw_date: Optional[date_type],
    counterparty_raw: Optional[str],
) -> Optional[Transaction]:
    if raw_date is None:
        return None

    candidates = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.amount == amount,
            func.date(Transaction.transaction_date) == raw_date,
        )
        .all()
    )
    for txn in candidates:
        if _infer_transaction_direction(txn) != direction:
            continue
        if _merchant_overlap(counterparty_raw, txn.merchant_clean or txn.merchant_raw):
            return txn
    return None


def find_match(
    db: Session,
    user_id: uuid.UUID,
    *,
    direction: TransactionDirection,
    amount: Decimal,
    utr: Optional[str],
    vpa: Optional[str],
    raw_timestamp: Optional[datetime],
    raw_date: Optional[date_type],
    counterparty_raw: Optional[str],
) -> Tuple[Optional[Transaction], Optional[int]]:
    """
    Runs the Section 4 tier hierarchy in order, strongest signal first.
    Direction is a hard filter baked into every tier above, not a separate
    pre-check, since each tier already needs it to compare candidates.
    Returns (matched_transaction_or_None, tier_or_None).
    """
    if utr:
        txn = _try_tier1_utr(db, user_id, utr, direction)
        if txn:
            return txn, 1

    if vpa:
        txn = _try_tier2_vpa(db, user_id, vpa, direction, amount, raw_timestamp)
        if txn:
            return txn, 2

    if raw_timestamp:
        txn = _try_tier3_time_and_merchant(db, user_id, direction, amount, raw_timestamp, counterparty_raw)
        if txn:
            return txn, 3

    effective_date = raw_date or (raw_timestamp.date() if raw_timestamp else None)
    if effective_date:
        txn = _try_tier4_date_and_merchant(db, user_id, direction, amount, effective_date, counterparty_raw)
        if txn:
            return txn, 4

    return None, None


def _enrich_canonical_transaction(
    txn: Transaction,
    merchant_raw: str,
    merchant_clean: Optional[str],
    category: Optional[str],
) -> None:
    """
    Section 4: "fields with better data quality from the new source UPDATE the
    canonical record." Only fills gaps — never overwrites an existing
    non-null value, since we have no confidence signal here to arbitrate
    between two non-null candidates from different sources.
    """
    if not txn.merchant_clean and merchant_clean:
        txn.merchant_clean = merchant_clean
    if not txn.category and category:
        txn.category = category


def ingest_or_match_transaction(
    db: Session,
    user: User,
    *,
    source: StatementSourceType,
    direction: TransactionDirection,
    amount: Decimal,
    transaction_date_hint: Optional[datetime],  # used only if creating new; matching uses raw_timestamp/raw_date
    idempotency_key: str,
    merchant_raw: str,
    merchant_clean: Optional[str] = None,
    category: Optional[str] = None,
    transaction_nature: TransactionNature = TransactionNature.expense,
    legacy_source_enum: TransactionSource = TransactionSource.csv,
    utr: Optional[str] = None,
    vpa: Optional[str] = None,
    raw_timestamp: Optional[datetime] = None,
    raw_date: Optional[date_type] = None,
    counterparty_raw: Optional[str] = None,
    currency: str = "INR",
    raw_row: Optional[dict] = None,
) -> Tuple[Transaction, TransactionSourceRecord, bool]:
    """
    Find-or-create entry point for the dedup pipeline. One call per parsed
    transaction line.

    `legacy_source_enum` exists only because Transaction.source (the stale
    gmail/sms/csv/aa enum) is still a NOT NULL column — callers must supply
    a value for it until that column is reconciled with StatementSourceType
    (see the docstring on StatementSourceType). For UPI-origin calls this
    will always be a slightly wrong fit until that reconciliation happens;
    flagged, not silently papered over.

    Returns (transaction, source_record, was_matched).
    Raises nothing on duplicate re-ingestion — returns the existing
    (transaction, source_record, True) instead, mirroring ingest_csv's
    existing duplicate-handling convention.
    """
    existing = _existing_source_record_for_idempotency_key(db, user.id, idempotency_key)
    if existing is not None:
        logger.debug(f"Duplicate source record skipped: {idempotency_key}")
        return existing.transaction, existing, True

    matched_txn, tier = find_match(
        db,
        user.id,
        direction=direction,
        amount=amount,
        utr=utr,
        vpa=vpa,
        raw_timestamp=raw_timestamp,
        raw_date=raw_date,
        counterparty_raw=counterparty_raw,
    )

    now = datetime.now(timezone.utc)

    if matched_txn is not None:
        _enrich_canonical_transaction(matched_txn, merchant_raw, merchant_clean, category)
        db.add(matched_txn)

        source_record = TransactionSourceRecord(
            id=uuid.uuid4(),
            user_id=user.id,
            transaction_id=matched_txn.id,
            source=source,
            direction=direction,
            utr=utr,
            vpa=vpa,
            raw_timestamp=raw_timestamp,
            raw_date=raw_date,
            raw_amount=amount,
            counterparty_raw=counterparty_raw,
            raw_row=raw_row,
            idempotency_key=idempotency_key,
            match_tier=tier,
            matched_at=now,
        )
        db.add(source_record)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = _existing_source_record_for_idempotency_key(db, user.id, idempotency_key)
            if existing is not None:
                return existing.transaction, existing, True
            raise

        logger.info(f"Matched new evidence to existing transaction: user={user.id}, tier={tier}, txn={matched_txn.id}")
        return matched_txn, source_record, True

    # No match — this becomes a new canonical transaction.
    resolved_date = raw_timestamp
    if resolved_date is None and raw_date is not None:
        resolved_date = datetime(raw_date.year, raw_date.month, raw_date.day, tzinfo=timezone.utc)
    if resolved_date is None:
        resolved_date = transaction_date_hint
    if resolved_date is None:
        raise ValueError("ingest_or_match_transaction: no usable transaction date (need raw_timestamp, raw_date, or transaction_date_hint)")

    new_txn = Transaction(
        id=uuid.uuid4(),
        user_id=user.id,
        source=legacy_source_enum,
        merchant_raw=merchant_raw,
        merchant_clean=merchant_clean,
        category=category,
        transaction_nature=transaction_nature,
        amount=amount,
        currency=currency,
        transaction_date=resolved_date,
        idempotency_key=idempotency_key,
        raw_source_data=raw_row,
    )
    db.add(new_txn)
    db.flush()  # get new_txn.id before building the source record

    source_record = TransactionSourceRecord(
        id=uuid.uuid4(),
        user_id=user.id,
        transaction_id=new_txn.id,
        source=source,
        direction=direction,
        utr=utr,
        vpa=vpa,
        raw_timestamp=raw_timestamp,
        raw_date=raw_date,
        raw_amount=amount,
        counterparty_raw=counterparty_raw,
        raw_row=raw_row,
        idempotency_key=idempotency_key,
        match_tier=None,
        matched_at=None,
    )
    db.add(source_record)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _existing_source_record_for_idempotency_key(db, user.id, idempotency_key)
        if existing is not None:
            return existing.transaction, existing, True
        raise

    logger.info(f"New canonical transaction created: user={user.id}, txn={new_txn.id}")
    return new_txn, source_record, False