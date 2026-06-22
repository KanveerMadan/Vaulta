"""
UPI Statement Parser Service — Phase 1.5 (post-Gmail/AA pivot)

Parses transaction-history PDFs exported from UPI apps (Google Pay, PhonePe, Paytm).
Unlike bank CSVs, these are PDFs with a consistent per-entry text block, extracted
via pdfplumber.

IMPORTANT — PDF text extraction quirk (verified against a real Google Pay export):
  pdfplumber strips inter-word spaces from this PDF's text layer (a font/encoding
  artifact, not a pdfplumber bug — confirmed both default and layout=True modes
  produce "PaidtoZEPTOMARKETPLACE..." with no spaces). This is NOT something we
  can fix at the extraction layer — regexes below match against the UNSPACED
  text directly, anchored on fixed label tokens ("Paidto", "Receivedfrom",
  "UPITransactionID:") rather than relying on whitespace boundaries.

  Counterparty names extracted this way are also unspaced (e.g. "ArjunMehra",
  "ZEPTOMARKETPLACEPRIVATELIMITED") and are de-mangled separately via
  _humanize_name() for display purposes — but classification (business vs.
  person) does NOT rely on casing/spacing heuristics, because real data shows
  this is unreliable: some personal names render in ALL CAPS too (e.g.
  "SUPREETKAUR" is a person, not a business). Classification instead runs the
  raw name through the merchant normalizer first; only names with NO confident
  merchant match fall back to peer-payment classification.

Supported sources:
  - Google Pay (verified against real export, Phase 1.5)
  - PhonePe (NOT YET IMPLEMENTED — stub raises UPIParseError with a clear message
    until a real sample PDF is available to verify the format against)
  - Paytm (NOT YET IMPLEMENTED — same as above)
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
    PHONEPE = "phonepe"
    PAYTM = "paytm"
    UNKNOWN = "unknown"


class TransactionNature(str, Enum):
    expense = "expense"
    income = "income"
    peer_payment_sent = "peer_payment_sent"
    peer_payment_received = "peer_payment_received"
    self_transfer = "self_transfer"


class UPIParseError(Exception):
    """Raised when a UPI statement cannot be parsed — surfaced as HTTP 422."""
    pass


@dataclass
class RawUPITransaction:
    merchant_raw: str               # De-mangled counterparty name, for display
    merchant_raw_unspaced: str       # Original glued string, for normalizer matching
    amount: Decimal
    transaction_date: datetime
    direction: str                   # "paid" | "received" | "self_transfer"
    utr: str                         # UPI Transaction ID — strongest dedup key
    linked_bank: str                 # e.g. "Kotak Mahindra Bank"
    linked_bank_last4: str
    idempotency_key: str
    raw_row: dict


# ─────────────────────────────────────────────
# Source detection
# ─────────────────────────────────────────────

def _detect_source(full_text: str) -> UPISource:
    """
    Identify which UPI app generated this statement.

    Detection strategy: brand names are not reliable anchors because
    Google Pay's branding appears only as a logo image (not extractable
    text) until the footer note at the bottom of each page. Instead we
    use structural text patterns that are unique to each app's format.

    Google Pay (verified against real export):
      - "UPITransactionID:" appears on every transaction row (unspaced).
      - "Paidto" / "Receivedfrom" direction labels are present.
      - The footer note contains "GooglePayapp" (space-stripped).
    PhonePe / Paytm: brand name appears as readable text — check first.
    """
    sample = full_text[:500].replace(" ", "").lower()

    if "phonepe" in sample:
        return UPISource.PHONEPE
    if "paytm" in sample:
        return UPISource.PAYTM

    # Google Pay: structural fingerprint — UTR label + direction label
    # Both appear in the very first transaction block, within first 500 chars.
    has_utr = "upitransactionid:" in sample
    has_direction = "paidto" in sample or "receivedfrom" in sample or "selftransferto" in sample
    if has_utr and has_direction:
        return UPISource.GOOGLE_PAY

    # Fallback: check full text for GPay footer note (last resort)
    full_stripped = full_text.replace(" ", "").lower()
    if "googlepay" in full_stripped or "googlepayapp" in full_stripped:
        return UPISource.GOOGLE_PAY

    return UPISource.UNKNOWN


# ─────────────────────────────────────────────
# Name de-mangling (display only — NOT used for classification)
# ─────────────────────────────────────────────

def _humanize_name(raw: str) -> str:
    """
    Best-effort insertion of spaces into glued PDF text, for display purposes.
    Does not need to be perfect — it's cosmetic. Classification logic below
    uses the merchant normalizer against the raw unspaced string instead,
    since that's more reliable than this heuristic.
    """
    s = raw.strip()
    # lowercase -> uppercase transition: "ArjunMehra" -> "Arjun Mehra"
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    # Known business suffixes glued at the end of an all-caps run
    for suffix, spaced in [
        ("PRIVATELIMITED", "PRIVATE LIMITED"),
        ("PVTLTD", "PVT LTD"),
    ]:
        s = s.replace(suffix, f" {spaced}")
    return re.sub(r"\s+", " ", s).strip()


# ─────────────────────────────────────────────
# Classification (business/merchant vs. peer payment)
# ─────────────────────────────────────────────

def _classify_counterparty(raw_unspaced: str) -> Tuple[Optional[str], Optional[str], float]:
    """
    Determine whether a counterparty is a recognized merchant or a person.

    Returns: (merchant_clean, category, confidence)
      - If merchant normalizer finds a confident match (>=0.5): treated as a
        real merchant, merchant_clean/category populated.
      - If no confident match: all None, signaling "peer payment" to the
        caller — default classification, user can recategorize as a real
        expense later if the normalizer was wrong.

    Design note: classification does NOT use casing/all-caps heuristics.
    Real Google Pay data shows personal names sometimes render in ALL CAPS
    (e.g. "SUPREETKAUR"), so casing alone is not a reliable signal. The
    normalizer match is the only thing classification trusts.
    """
    normalized = normalize(raw_unspaced)
    if normalized.confidence >= 0.5:
        return normalized.merchant_clean, normalized.category, normalized.confidence
    return None, None, 0.0


# ─────────────────────────────────────────────
# Amount / date parsing
# ─────────────────────────────────────────────

def _parse_amount(raw: str) -> Optional[Decimal]:
    cleaned = raw.replace(",", "").replace("₹", "").strip()
    try:
        value = Decimal(cleaned)
        return value if value > 0 else None
    except InvalidOperation:
        return None


def _parse_gpay_date(date_str: str, time_str: str) -> datetime:
    """
    Parses Google Pay's glued date format: "04May,2026" + "05:23AM"
    -> datetime(2026, 5, 4, 5, 23)
    """
    cleaned_date = re.sub(r"(\d{2})([A-Za-z]+),?(\d{4})", r"\1 \2 \3", date_str)
    cleaned_time = re.sub(r"(\d{2}:\d{2})([AP]M)", r"\1 \2", time_str)
    combined = f"{cleaned_date} {cleaned_time}"
    return datetime.strptime(combined, "%d %b %Y %I:%M %p")


def _make_idempotency_key(source: str, utr: str) -> str:
    """UTR is globally unique per UPI transaction — strongest possible dedup key."""
    return hashlib.sha256(f"upi|{source}|{utr}".encode()).hexdigest()


# ─────────────────────────────────────────────
# Google Pay parser (VERIFIED against real export)
# ─────────────────────────────────────────────

# Anchored on fixed label tokens, not whitespace — required because this PDF's
# text layer has no inter-word spaces (see module docstring).
_GPAY_PATTERN = re.compile(
    r"(\d{2}[A-Za-z]+,?\d{4})\s*"                          # date: "04May,2026"
    r"(Paidto|Receivedfrom|Selftransferto)"                 # direction
    r"(.+?)"                                                 # counterparty (lazy)
    r"₹([\d,]+\.?\d*)\s*"                                   # amount
    r"(\d{2}:\d{2}[AP]M)\s*"                                # time
    r"UPITransactionID:(\d+)\s*"                            # UTR
    r"(Paidby|Paidto)(.+?)(\d{3,4})"                        # linked bank + last 3-4 digits
)


def _parse_google_pay(full_text: str) -> List[RawUPITransaction]:
    transactions = []
    matches = _GPAY_PATTERN.findall(full_text)

    for match in matches:
        (date_str, direction_raw, counterparty_raw, amount_str,
         time_str, utr, _bank_prefix, bank_name_raw, bank_last_digits) = match

        try:
            txn_date = _parse_gpay_date(date_str, time_str)
        except ValueError as e:
            logger.warning(f"Google Pay row: failed to parse date {date_str!r}+{time_str!r}: {e} — skipping")
            continue

        amount = _parse_amount(amount_str)
        if not amount:
            continue

        counterparty_raw = counterparty_raw.strip()

        if direction_raw == "Selftransferto":
            direction = "self_transfer"
        elif direction_raw == "Paidto":
            direction = "paid"
        else:  # "Receivedfrom"
            direction = "received"

        idem_key = _make_idempotency_key("google_pay", utr)

        transactions.append(RawUPITransaction(
            merchant_raw=_humanize_name(counterparty_raw),
            merchant_raw_unspaced=counterparty_raw,
            amount=amount,
            transaction_date=txn_date,
            direction=direction,
            utr=utr,
            linked_bank=_humanize_name(bank_name_raw.strip()),
            linked_bank_last4=bank_last_digits,
            idempotency_key=idem_key,
            raw_row={
                "date": date_str, "time": time_str, "direction": direction_raw,
                "counterparty": counterparty_raw, "amount": amount_str, "utr": utr,
            },
        ))

    return transactions


# ─────────────────────────────────────────────
# PhonePe / Paytm — STUBS, pending real sample PDFs
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
    UPISource.PHONEPE: _parse_phonepe,
    UPISource.PAYTM: _parse_paytm,
}


def parse_upi_statement(file_bytes: bytes, filename: str = "") -> Tuple[UPISource, List[RawUPITransaction]]:
    """
    Parse a UPI app statement PDF.

    Returns:
        (UPISource, List[RawUPITransaction])

    Raises:
        UPIParseError — unrecognized source, or a recognized-but-unimplemented
        source (PhonePe/Paytm currently), or malformed/empty PDF.
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