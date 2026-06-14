"""
CSV Parser Service — Phase 1

Parses bank statement CSV exports from major Indian banks into normalized
Transaction records. Each bank has its own column layout, date format,
and debit/credit encoding — handled per-bank below.

Supported banks:
  - HDFC Bank
  - ICICI Bank
  - SBI (State Bank of India)
  - Axis Bank
  - Kotak Mahindra Bank

Usage:
    from app.services.csv_parser import parse_csv, DetectedBank

    bank, transactions = parse_csv(file_bytes, filename="hdfc_statement.csv")
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class DetectedBank(str, Enum):
    HDFC = "hdfc"
    ICICI = "icici"
    SBI = "sbi"
    AXIS = "axis"
    KOTAK = "kotak"
    UNKNOWN = "unknown"


class CSVParseError(Exception):
    """Raised when a CSV file cannot be parsed — surfaced to the API as a 422."""
    pass


@dataclass
class RawTransaction:
    """Intermediate representation before merchant normalization."""
    merchant_raw: str
    amount: Decimal
    transaction_date: datetime
    idempotency_key: str
    raw_row: dict  # Original CSV row for raw_source_data field


# ─────────────────────────────────────────────
# Bank detection
# ─────────────────────────────────────────────

def _detect_bank(header_row: List[str]) -> DetectedBank:
    """
    Identify the bank from the CSV header columns.
    Headers are lowercased and stripped before comparison.
    """
    headers = {h.lower().strip() for h in header_row}

    # HDFC: "Date", "Narration", "Value Dat", "Debit Amount", "Credit Amount", "Chq/Ref Number", "Closing Balance"
    if {"narration", "debit amount", "credit amount", "closing balance"}.issubset(headers):
        return DetectedBank.HDFC

    # ICICI: "S No.", "Value Date", "Transaction Date", "Cheque Number", "Transaction Remarks", "Withdrawal Amount (INR )", "Deposit Amount (INR )", "Balance (INR )"
    if {"transaction remarks", "withdrawal amount (inr )", "deposit amount (inr )"}.issubset(headers):
        return DetectedBank.ICICI

    # SBI: "Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Debit", "Credit", "Balance"
    if {"txn date", "description", "ref no./cheque no.", "debit", "credit", "balance"}.issubset(headers):
        return DetectedBank.SBI

    # Axis: "Tran Date", "Chq No", "Particulars", "Debit", "Credit", "Balance"
    if {"tran date", "particulars", "debit", "credit", "balance"}.issubset(headers):
        return DetectedBank.AXIS

    # Kotak: "Transaction Date", "Value Date", "Description", "Chq/Ref Number", "Debit", "Credit", "Balance"
    if {"transaction date", "description", "chq/ref number", "debit", "credit", "balance"}.issubset(headers):
        return DetectedBank.KOTAK

    return DetectedBank.UNKNOWN


# ─────────────────────────────────────────────
# Amount parsing helpers
# ─────────────────────────────────────────────

def _parse_amount(raw: str) -> Optional[Decimal]:
    """
    Parse an amount string from any bank format to Decimal.
    Handles: "1,234.56", "1234.56", "1,234", "", "Dr", commas.
    Returns None for empty/non-numeric cells.
    """
    if not raw or not raw.strip():
        return None
    # Remove commas, spaces, currency symbols
    cleaned = re.sub(r"[,\s₹$]", "", raw.strip())
    # Some banks suffix with "Dr" or "Cr"
    cleaned = re.sub(r"(Dr|Cr)$", "", cleaned, flags=re.IGNORECASE).strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
        return value if value > 0 else None
    except InvalidOperation:
        return None


def _parse_date(raw: str, formats: List[str]) -> datetime:
    """Try each format in order, raise CSVParseError if none match."""
    raw = raw.strip()
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise CSVParseError(f"Cannot parse date '{raw}' with formats {formats}")


def _make_idempotency_key(source: str, bank: str, date: str, merchant: str, amount: str) -> str:
    """SHA256 of deterministic fields — prevents duplicate inserts on re-upload."""
    payload = f"{source}|{bank}|{date}|{merchant}|{amount}"
    return hashlib.sha256(payload.encode()).hexdigest()


# ─────────────────────────────────────────────
# Per-bank parsers
# ─────────────────────────────────────────────

def _parse_hdfc(rows: List[dict]) -> List[RawTransaction]:
    transactions = []
    date_formats = ["%d/%m/%y", "%d/%m/%Y"]

    for i, row in enumerate(rows):
        try:
            date_str = row.get("Date", "").strip()
            if not date_str:
                continue

            narration = row.get("Narration", "").strip()
            if not narration:
                continue

            debit = _parse_amount(row.get("Debit Amount", ""))
            # We only import debits (money out) for now — credits are income, Phase 3 feature
            if not debit:
                continue

            txn_date = _parse_date(date_str, date_formats)
            idem_key = _make_idempotency_key("csv", "hdfc", date_str, narration, str(debit))

            transactions.append(RawTransaction(
                merchant_raw=narration,
                amount=debit,
                transaction_date=txn_date,
                idempotency_key=idem_key,
                raw_row=dict(row),
            ))
        except CSVParseError as e:
            logger.warning(f"HDFC row {i}: {e} — skipping")
        except Exception as e:
            logger.warning(f"HDFC row {i} unexpected error: {e} — skipping")

    return transactions


def _parse_icici(rows: List[dict]) -> List[RawTransaction]:
    transactions = []
    date_formats = ["%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"]

    for i, row in enumerate(rows):
        try:
            date_str = row.get("Transaction Date", row.get("Value Date", "")).strip()
            if not date_str:
                continue

            remarks = row.get("Transaction Remarks", "").strip()
            if not remarks:
                continue

            # ICICI: "Withdrawal Amount (INR )" for debits
            withdrawal_key = next((k for k in row if "withdrawal" in k.lower()), None)
            if not withdrawal_key:
                continue
            debit = _parse_amount(row.get(withdrawal_key, ""))
            if not debit:
                continue

            txn_date = _parse_date(date_str, date_formats)
            idem_key = _make_idempotency_key("csv", "icici", date_str, remarks, str(debit))

            transactions.append(RawTransaction(
                merchant_raw=remarks,
                amount=debit,
                transaction_date=txn_date,
                idempotency_key=idem_key,
                raw_row=dict(row),
            ))
        except CSVParseError as e:
            logger.warning(f"ICICI row {i}: {e} — skipping")
        except Exception as e:
            logger.warning(f"ICICI row {i} unexpected error: {e} — skipping")

    return transactions


def _parse_sbi(rows: List[dict]) -> List[RawTransaction]:
    transactions = []
    date_formats = ["%d %b %Y", "%d/%m/%Y", "%d-%m-%Y"]

    for i, row in enumerate(rows):
        try:
            date_str = row.get("Txn Date", "").strip()
            if not date_str:
                continue

            description = row.get("Description", "").strip()
            if not description:
                continue

            debit = _parse_amount(row.get("Debit", ""))
            if not debit:
                continue

            txn_date = _parse_date(date_str, date_formats)
            idem_key = _make_idempotency_key("csv", "sbi", date_str, description, str(debit))

            transactions.append(RawTransaction(
                merchant_raw=description,
                amount=debit,
                transaction_date=txn_date,
                idempotency_key=idem_key,
                raw_row=dict(row),
            ))
        except CSVParseError as e:
            logger.warning(f"SBI row {i}: {e} — skipping")
        except Exception as e:
            logger.warning(f"SBI row {i} unexpected error: {e} — skipping")

    return transactions


def _parse_axis(rows: List[dict]) -> List[RawTransaction]:
    transactions = []
    date_formats = ["%d-%m-%Y", "%d/%m/%Y", "%d %b %Y"]

    for i, row in enumerate(rows):
        try:
            date_str = row.get("Tran Date", "").strip()
            if not date_str:
                continue

            particulars = row.get("Particulars", "").strip()
            if not particulars:
                continue

            debit = _parse_amount(row.get("Debit", ""))
            if not debit:
                continue

            txn_date = _parse_date(date_str, date_formats)
            idem_key = _make_idempotency_key("csv", "axis", date_str, particulars, str(debit))

            transactions.append(RawTransaction(
                merchant_raw=particulars,
                amount=debit,
                transaction_date=txn_date,
                idempotency_key=idem_key,
                raw_row=dict(row),
            ))
        except CSVParseError as e:
            logger.warning(f"Axis row {i}: {e} — skipping")
        except Exception as e:
            logger.warning(f"Axis row {i} unexpected error: {e} — skipping")

    return transactions


def _parse_kotak(rows: List[dict]) -> List[RawTransaction]:
    transactions = []
    date_formats = ["%d-%m-%yyyy", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"]

    for i, row in enumerate(rows):
        try:
            date_str = row.get("Transaction Date", "").strip()
            if not date_str:
                continue

            description = row.get("Description", "").strip()
            if not description:
                continue

            debit = _parse_amount(row.get("Debit", ""))
            if not debit:
                continue

            txn_date = _parse_date(date_str, date_formats)
            idem_key = _make_idempotency_key("csv", "kotak", date_str, description, str(debit))

            transactions.append(RawTransaction(
                merchant_raw=description,
                amount=debit,
                transaction_date=txn_date,
                idempotency_key=idem_key,
                raw_row=dict(row),
            ))
        except CSVParseError as e:
            logger.warning(f"Kotak row {i}: {e} — skipping")
        except Exception as e:
            logger.warning(f"Kotak row {i} unexpected error: {e} — skipping")

    return transactions


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

BANK_PARSERS = {
    DetectedBank.HDFC: _parse_hdfc,
    DetectedBank.ICICI: _parse_icici,
    DetectedBank.SBI: _parse_sbi,
    DetectedBank.AXIS: _parse_axis,
    DetectedBank.KOTAK: _parse_kotak,
}


def parse_csv(
    file_bytes: bytes,
    filename: str = "",
) -> Tuple[DetectedBank, List[RawTransaction]]:
    """
    Parse a bank statement CSV into RawTransaction objects.

    Returns:
        (DetectedBank, List[RawTransaction])

    Raises:
        CSVParseError — if bank cannot be detected or file is malformed.
        The caller (route handler) surfaces this as HTTP 422.

    Note:
        Merchant normalization is NOT done here — RawTransaction.merchant_raw
        is the verbatim string from the bank. The normalizer runs separately
        so it can be tested and improved independently.
    """
    try:
        # Decode bytes — most Indian bank exports are UTF-8 or Windows-1252
        try:
            text = file_bytes.decode("utf-8-sig")  # -sig strips BOM if present
        except UnicodeDecodeError:
            text = file_bytes.decode("windows-1252")

        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)

        if not rows:
            raise CSVParseError("CSV file is empty or has no data rows")

        fieldnames = reader.fieldnames or []
        bank = _detect_bank(list(fieldnames))

        if bank == DetectedBank.UNKNOWN:
            raise CSVParseError(
                f"Bank format not recognized from columns: {list(fieldnames)}. "
                "Supported: HDFC, ICICI, SBI, Axis, Kotak."
            )

        parser = BANK_PARSERS[bank]
        transactions = parser(rows)

        if not transactions:
            raise CSVParseError(
                f"No debit transactions found in {bank.value.upper()} statement. "
                "Check that the file contains spending transactions."
            )

        logger.info(
            f"CSV parse complete: bank={bank.value}, file={filename!r}, "
            f"rows={len(rows)}, transactions_extracted={len(transactions)}"
        )
        return bank, transactions

    except CSVParseError:
        raise
    except Exception as e:
        raise CSVParseError(f"Failed to read CSV file: {e}") from e