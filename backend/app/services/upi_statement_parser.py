"""
UPI Statement Parser Service — Phase 1.5 (post-Gmail/AA pivot)

Parses transaction-history PDFs exported from UPI apps (Google Pay, PhonePe, Paytm).

FORMAT NOTE (verified against real May 2026 Google Pay export):
  This PDF renders text WITH spaces — "Paid to ZEPTO MARKETPLACE PRIVATE LIMITED",
  "UPI Transaction ID: 612456562367", "Paid by IndusInd Bank 8250".
  An earlier export format stripped inter-word spaces; that version is no longer
  observed. The parser below handles the spaced format. If a future export regresses
  to the no-space format, the regexes will need revisiting.

  Detection: "Google Pay" appears only as a logo image — pdfplumber cannot read it.
  Detection instead uses structural text patterns unique to GPay statements
  ("UPI Transaction ID:" combined with "Paid to"/"Received from" direction labels).

Supported sources:
  - Google Pay (verified against real 5-page export, 44 transactions)
  - PhonePe (NOT YET IMPLEMENTED — stub raises UPIParseError)
  - Paytm  (NOT YET IMPLEMENTED — stub raises UPIParseError)
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import List, Optional, Tuple

import pdfplumber

from app.services.merchant_normalizer import normalize

logger = logging.getLogger(__name__)


class UPISource(str, Enum):
    GOOGLE_PAY = "google_pay"
    PHONEPE    = "phonepe"
    PAYTM      = "paytm"
    UNKNOWN    = "unknown"


class TransactionNature(str, Enum):
    expense              = "expense"
    income               = "income"
    peer_payment_sent    = "peer_payment_sent"
    peer_payment_received = "peer_payment_received"
    self_transfer        = "self_transfer"


class UPIParseError(Exception):
    """Raised when a UPI statement cannot be parsed — surfaced as HTTP 422."""
    pass


@dataclass
class RawUPITransaction:
    merchant_raw: str           # humanized counterparty name, for display
    merchant_raw_unspaced: str  # original string for normalizer matching
    amount: Decimal
    transaction_date: datetime
    direction: str              # "paid" | "received" | "self_transfer"
    utr: str
    linked_bank: str
    linked_bank_last4: str
    idempotency_key: str
    raw_row: dict


# ─────────────────────────────────────────────
# Source detection
# ─────────────────────────────────────────────

# Structural fingerprint: GPay statements always have "UPI Transaction ID:"
# AND at least one of the direction labels. PhonePe/Paytm have different
# label text (verified when their formats are added). The Google Pay logo
# is an image and cannot be detected via text extraction.
_GPAY_STRUCTURAL_MARKERS = re.compile(
    r"UPI Transaction ID:\s*\d+",
    re.IGNORECASE,
)
_GPAY_DIRECTION_MARKERS = re.compile(
    r"\b(Paid to|Received from|Self transfer to)\b",
    re.IGNORECASE,
)


def _detect_source(full_text: str) -> UPISource:
    # PhonePe and Paytm checks first — if either brand name is in the text
    # as readable characters, trust it. GPay detection is structural since
    # its branding is image-only.
    lower = full_text.lower()
    if "phonepe" in lower:
        return UPISource.PHONEPE
    if "paytm" in lower:
        return UPISource.PAYTM

    has_utr     = bool(_GPAY_STRUCTURAL_MARKERS.search(full_text))
    has_direction = bool(_GPAY_DIRECTION_MARKERS.search(full_text))
    if has_utr and has_direction:
        return UPISource.GOOGLE_PAY

    return UPISource.UNKNOWN


# ─────────────────────────────────────────────
# Name humanization (display only)
# ─────────────────────────────────────────────

def _humanize_name(raw: str) -> str:
    """
    Best-effort cleanup for display. In the spaced format the name already
    has spaces; this mainly handles title-casing and known suffix patterns.
    Classification uses the raw string against the normalizer, not this.
    """
    s = raw.strip()
    # camelCase split: "ArjunMehra" → "Arjun Mehra" (rare in spaced format but safe)
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    for suffix, spaced in [
        ("PRIVATELIMITED", "PRIVATE LIMITED"),
        ("PVTLTD", "PVT LTD"),
    ]:
        s = s.replace(suffix, f" {spaced}")
    return re.sub(r"\s+", " ", s).strip()


# ─────────────────────────────────────────────
# Amount / date helpers
# ─────────────────────────────────────────────

def _parse_amount(raw: str) -> Optional[Decimal]:
    cleaned = raw.replace(",", "").replace("₹", "").strip()
    try:
        v = Decimal(cleaned)
        return v if v > 0 else None
    except InvalidOperation:
        return None


def _parse_gpay_date(date_str: str, time_str: str) -> datetime:
    """
    Handles the spaced format: "04 May, 2026" + "05:23 AM"
    Also tolerates the legacy no-space format: "04May,2026" + "05:23AM"
    """
    d = date_str.strip().rstrip(",")
    t = time_str.strip()

    # Normalise: insert space before month name if missing ("04May" → "04 May")
    d = re.sub(r"(\d{2})([A-Za-z])", r"\1 \2", d)
    # Normalise: insert space before AM/PM if missing ("05:23AM" → "05:23 AM")
    t = re.sub(r"(\d{2}:\d{2})([AP]M)", r"\1 \2", t)

    combined = f"{d} {t}"
    for fmt in ("%d %b %Y %I:%M %p", "%d %b, %Y %I:%M %p"):
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse GPay date/time: {date_str!r} {time_str!r}")


def _make_idempotency_key(source: str, utr: str) -> str:
    return hashlib.sha256(f"upi|{source}|{utr}".encode()).hexdigest()


# ─────────────────────────────────────────────
# Google Pay line-by-line parser
# ─────────────────────────────────────────────

# Matches the date line: "04 May, 2026" or "04May,2026"
_DATE_RE = re.compile(r"^\d{2}\s*[A-Za-z]+,?\s*\d{4}$")
# Matches the time line: "05:23 AM" or "05:23AM"
_TIME_RE = re.compile(r"^\d{2}:\d{2}\s*[AP]M$")
# Matches direction + counterparty
_DIRECTION_RE = re.compile(
    r"^(Paid to|Received from|Self transfer to)\s+(.+)$",
    re.IGNORECASE,
)
# Matches UTR line: "UPI Transaction ID: 612456562367"
_UTR_RE = re.compile(r"UPI Transaction ID:\s*(\d+)", re.IGNORECASE)
# Matches bank line: "Paid by Kotak Mahindra Bank 9259" or "Paid to Kotak..."
_BANK_RE = re.compile(
    r"^(?:Paid by|Paid to)\s+(.+?)\s+(\d{3,4})$",
    re.IGNORECASE,
)
# Matches amount line: "₹129" or "₹1,425" or "₹430.01"
_AMOUNT_RE = re.compile(r"^₹[\d,]+\.?\d*$")

# Lines that are page headers/footers — skip them
_SKIP_RE = re.compile(
    r"(Transaction statement|Note: This statement|Page \d+ of \d+|"
    r"Powered by|Date & time|Transaction details|Amount|"
    r"\d{10},\s*.+@.+)",
    re.IGNORECASE,
)


def _parse_google_pay(full_text: str) -> List[RawUPITransaction]:
    """
    Line-by-line state machine parser for the Google Pay spaced-text format.
    Each transaction block has a fixed structure:
      1. date line        "04 May, 2026"
      2. time line        "05:23 AM"
      3. direction line   "Paid to ZEPTO MARKETPLACE PRIVATE LIMITED"
      4. UTR line         "UPI Transaction ID: 612456562367"
      5. bank line        "Paid by IndusInd Bank 8250"
      6. amount line      "₹129"
    """
    lines = [l.strip() for l in full_text.splitlines()]
    lines = [l for l in lines if l and not _SKIP_RE.search(l)]

    transactions: List[RawUPITransaction] = []

    # State per transaction block
    date_str     = None
    time_str     = None
    direction    = None
    counterparty = None
    utr          = None
    bank_name    = None
    bank_last4   = None
    amount       = None

    def _flush():
        nonlocal date_str, time_str, direction, counterparty, utr
        nonlocal bank_name, bank_last4, amount

        if not all([date_str, time_str, direction, counterparty, utr, amount]):
            # Incomplete block — reset and move on
            date_str = time_str = direction = counterparty = None
            utr = bank_name = bank_last4 = amount = None
            return

        try:
            txn_date = _parse_gpay_date(date_str, time_str)
        except ValueError as e:
            logger.warning(f"GPay: date parse failed {date_str!r} {time_str!r}: {e} — skipping")
            date_str = time_str = direction = counterparty = None
            utr = bank_name = bank_last4 = amount = None
            return

        idem = _make_idempotency_key("google_pay", utr)

        transactions.append(RawUPITransaction(
            merchant_raw=_humanize_name(counterparty),
            merchant_raw_unspaced=counterparty.replace(" ", ""),
            amount=amount,
            transaction_date=txn_date,
            direction=direction,
            utr=utr,
            linked_bank=bank_name or "",
            linked_bank_last4=bank_last4 or "",
            idempotency_key=idem,
            raw_row={
                "date": date_str, "time": time_str, "direction": direction,
                "counterparty": counterparty, "amount": str(amount), "utr": utr,
                "bank": bank_name, "bank_last4": bank_last4,
            },
        ))

        date_str = time_str = direction = counterparty = None
        utr = bank_name = bank_last4 = amount = None

    for line in lines:
        # Date line starts a new block — flush any pending block first
        if _DATE_RE.match(line):
            _flush()
            date_str = line
            continue

        if date_str is None:
            # Haven't seen a date yet — skip until we do
            continue

        if _TIME_RE.match(line) and time_str is None:
            time_str = line
            continue

        m = _DIRECTION_RE.match(line)
        if m and direction is None:
            raw_dir = m.group(1).lower()
            if "self transfer" in raw_dir:
                direction = "self_transfer"
            elif "paid to" in raw_dir:
                direction = "paid"
            else:
                direction = "received"
            counterparty = m.group(2).strip()
            continue

        m = _UTR_RE.search(line)
        if m and utr is None:
            utr = m.group(1)
            continue

        m = _BANK_RE.match(line)
        if m and bank_name is None:
            bank_name  = m.group(1).strip()
            bank_last4 = m.group(2)
            continue

        if _AMOUNT_RE.match(line) and amount is None:
            amount = _parse_amount(line)
            continue

    # Flush the final block
    _flush()

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


def parse_upi_statement(
    file_bytes: bytes,
    filename: str = "",
) -> Tuple[UPISource, List[RawUPITransaction]]:
    """
    Parse a UPI app statement PDF.

    Returns (UPISource, List[RawUPITransaction]).
    Raises UPIParseError on unrecognized source, unimplemented source,
    or malformed/empty PDF.
    """
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            full_text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n"
    except Exception as e:
        raise UPIParseError(f"Could not read PDF file: {e}") from e

    if not full_text.strip():
        raise UPIParseError(
            "No text found in this PDF. If this is a scanned/image-based statement, "
            "text extraction is not supported for UPI statements."
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
            f"No transactions found in this "
            f"{source.value.replace('_', ' ').title()} statement. "
            "Check that the file is a transaction history export, not a payment receipt."
        )

    logger.info(
        f"UPI statement parsed: source={source.value}, file={filename!r}, "
        f"transactions={len(transactions)}"
    )
    return source, transactions