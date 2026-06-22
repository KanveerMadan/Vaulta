"""
UPI Statement Parser Service — Phase 1.5 (post-Gmail/AA pivot)

Parses transaction-history PDFs exported from UPI apps (Google Pay, PhonePe, Paytm).
Uses pymupdf (fitz) for PDF text extraction — correctly handles font encoding on Linux.

pymupdf extracts this PDF with spaces: "Paid to ZEPTO MARKETPLACE PRIVATE LIMITED",
"UPI Transaction ID: 612456562367". Regexes match the spaced format.

Supported sources:
  - Google Pay (verified against real export, Phase 1.5)
  - PhonePe (NOT YET IMPLEMENTED — stub raises UPIParseError)
  - Paytm  (NOT YET IMPLEMENTED — stub raises UPIParseError)
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import List, Optional, Tuple

import fitz  # pymupdf

from app.services.merchant_normalizer import normalize

logger = logging.getLogger(__name__)


class UPISource(str, Enum):
    GOOGLE_PAY = "google_pay"
    PHONEPE    = "phonepe"
    PAYTM      = "paytm"
    UNKNOWN    = "unknown"


class TransactionNature(str, Enum):
    expense               = "expense"
    income                = "income"
    peer_payment_sent     = "peer_payment_sent"
    peer_payment_received = "peer_payment_received"
    self_transfer         = "self_transfer"


class UPIParseError(Exception):
    """Raised when a UPI statement cannot be parsed — surfaced as HTTP 422."""
    pass


@dataclass
class RawUPITransaction:
    merchant_raw: str            # counterparty name with spaces, for display
    merchant_raw_unspaced: str   # spaces removed, for normalizer matching
    amount: Decimal
    transaction_date: datetime
    direction: str               # "paid" | "received" | "self_transfer"
    utr: str
    linked_bank: str
    linked_bank_last4: str
    idempotency_key: str
    raw_row: dict


# ─────────────────────────────────────────────
# Source detection
# ─────────────────────────────────────────────

def _detect_source(full_text: str) -> UPISource:
    lower = full_text.lower()

    if "phonepe" in lower:
        return UPISource.PHONEPE
    if "paytm" in lower:
        return UPISource.PAYTM
    if "google pay" in lower or "googlepay" in lower:
        return UPISource.GOOGLE_PAY
    # Structural fallback
    if "upi transaction id" in lower and ("paid to" in lower or "received from" in lower):
        return UPISource.GOOGLE_PAY

    return UPISource.UNKNOWN


# ─────────────────────────────────────────────
# Amount / date helpers
# ─────────────────────────────────────────────

def _parse_amount(raw: str) -> Optional[Decimal]:
    cleaned = raw.replace(",", "").replace("₹", "").strip()
    try:
        value = Decimal(cleaned)
        return value if value > 0 else None
    except InvalidOperation:
        return None


def _make_idempotency_key(source: str, utr: str) -> str:
    return hashlib.sha256(f"upi|{source}|{utr}".encode()).hexdigest()


# ─────────────────────────────────────────────
# Google Pay parser
# ─────────────────────────────────────────────

# pymupdf extracts this PDF with spaces.
# Each transaction block looks like:
#   04 May, 2026\n05:23 AM\nPaid to ZEPTO MARKETPLACE PRIVATE LIMITED\nUPI Transaction ID: 612456562367\nPaid by IndusInd Bank 8250\n₹129
_GPAY_PATTERN = re.compile(
    r"(\d{2}\s+[A-Za-z]+,?\s*\d{4})\n"           # date: "04 May, 2026"
    r"(\d{2}:\d{2}\s*[AP]M)\n"                    # time: "05:23 AM"
    r"(Paid to|Received from|Self transfer to)\s+" # direction
    r"(.+?)\n"                                     # counterparty
    r"UPI Transaction ID:\s*(\d+)\n"               # UTR
    r"(?:Paid by|Paid to)\s+(.+?)\s+(\d{3,4})\n"  # bank + last digits
    r"₹([\d,]+\.?\d*)",                            # amount
    re.MULTILINE,
)


def _parse_google_pay(full_text: str) -> List[RawUPITransaction]:
    transactions = []
    matches = _GPAY_PATTERN.findall(full_text)
    logger.info(f"GPay regex matches: {len(matches)}")

    for match in matches:
        (date_str, time_str, direction_raw, counterparty_raw,
         utr, bank_name_raw, bank_last_digits, amount_str) = match

        amount = _parse_amount(amount_str)
        if not amount:
            continue

        # Parse date + time
        try:
            date_clean = re.sub(r"\s+", " ", date_str.strip().rstrip(","))
            time_clean = re.sub(r"\s+", " ", time_str.strip())
            combined = f"{date_clean} {time_clean}"
            txn_date = None
            for fmt in ("%d %b %Y %I:%M %p", "%d %b, %Y %I:%M %p"):
                try:
                    txn_date = datetime.strptime(combined, fmt)
                    break
                except ValueError:
                    continue
            if txn_date is None:
                logger.warning(f"GPay: could not parse date {combined!r} — skipping")
                continue
        except Exception as e:
            logger.warning(f"GPay: date error {e} — skipping")
            continue

        direction_lower = direction_raw.lower()
        if "self transfer" in direction_lower:
            direction = "self_transfer"
        elif "paid to" in direction_lower:
            direction = "paid"
        else:
            direction = "received"

        counterparty = counterparty_raw.strip()
        idem_key = _make_idempotency_key("google_pay", utr)

        transactions.append(RawUPITransaction(
            merchant_raw=counterparty,
            merchant_raw_unspaced=counterparty.replace(" ", ""),
            amount=amount,
            transaction_date=txn_date,
            direction=direction,
            utr=utr,
            linked_bank=bank_name_raw.strip(),
            linked_bank_last4=bank_last_digits,
            idempotency_key=idem_key,
            raw_row={
                "date": date_str, "time": time_str, "direction": direction_raw,
                "counterparty": counterparty, "amount": amount_str, "utr": utr,
            },
        ))

    return transactions


# ─────────────────────────────────────────────
# PhonePe / Paytm — stubs
# ─────────────────────────────────────────────

def _parse_phonepe(full_text: str) -> List[RawUPITransaction]:
    raise UPIParseError(
        "PhonePe statement parsing is not yet implemented. "
        "This format is pending verification against a real exported PDF."
    )


def _parse_paytm(full_text: str) -> List[RawUPITransaction]:
    raise UPIParseError(
        "Paytm statement parsing is not yet implemented. "
        "This format is pending verification against a real exported PDF."
    )


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

_SOURCE_PARSERS = {
    UPISource.GOOGLE_PAY: _parse_google_pay,
    UPISource.PHONEPE:    _parse_phonepe,
    UPISource.PAYTM:      _parse_paytm,
}


def parse_upi_statement(file_bytes: bytes, filename: str = "") -> Tuple[UPISource, List[RawUPITransaction]]:
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        doc.close()
    except Exception as e:
        raise UPIParseError(f"Could not read PDF file: {e}") from e

    if not full_text.strip():
        raise UPIParseError(
            "No text found in this PDF. If this is a scanned/image-based statement, "
            "text extraction is not yet supported for UPI statements."
        )

    source = _detect_source(full_text)
    if source == UPISource.UNKNOWN:
        raise UPIParseError(
            "Could not identify which app this statement is from. "
            "Supported: Google Pay (PhonePe and Paytm coming soon)."
        )

    parser = _SOURCE_PARSERS[source]
    transactions = parser(full_text)

    if not transactions:
        raise UPIParseError(
            f"No transactions found in this {source.value.replace('_', ' ').title()} statement."
        )

    logger.info(f"UPI statement parsed: source={source.value}, file={filename!r}, transactions={len(transactions)}")
    return source, transactions