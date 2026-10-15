"""
Stable identities derived from sanitized narrations: which merchant or which
person a transaction is with. Shared by refunds, recurring detection,
people and learned rules so they all group the same way.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

from app.models.transaction import Transaction, TransactionNature

# Personal UPI IDs arrive masked by the browser (frontend/src/import/pii.js)
MASKED_VPA = re.compile(r"\b([A-Z]|X)\*\*\*@[a-z][a-z0-9.]*", re.IGNORECASE)

_NOISE_WORDS = {
    "upi", "imps", "neft", "rtgs", "p2a", "p2m", "dr", "cr", "sent", "received", "payment", "pay",
    "paid", "to", "from", "by", "transfer", "trf", "self", "mr", "mrs", "ms", "bank", "ltd", "via",
    "split", "share", "rent", "dinner", "lunch", "tea", "milk",
}
_BANK_WORDS = re.compile(r"\b(bank|bk|hdfc|icici|sbi|axis|kotak|paytm|ybl|yes)\b", re.IGNORECASE)
_PREFIX = re.compile(r"^(paid to|received from|money sent to|money received from|sent to|transfer to)\s+", re.IGNORECASE)


def merchant_key(txn: Transaction) -> str:
    """Normalized merchant if known, else the narration minus numbers/masks and punctuation."""
    if txn.merchant_clean:
        return txn.merchant_clean.strip().lower()
    raw = MASKED_VPA.sub(" ", txn.merchant_raw or "")
    raw = re.sub(r"X{3,}|\d+", " ", raw)
    return " ".join(re.split(r"[^a-z]+", raw.lower())).strip()[:80]


def _name_token(text: str) -> Optional[str]:
    """First narration segment that reads like a person's name (1–4 alphabetic words)."""
    text = re.sub(r"\bX{3,}\w*|\d+", " ", MASKED_VPA.sub(" ", text))
    for segment in re.split(r"[-/|]", text):
        segment = _PREFIX.sub("", segment.strip())
        words = [w for w in segment.split() if w.isalpha()]
        if not words or len(words) > 4 or len(words) != len(segment.split()):
            continue
        if _BANK_WORDS.search(segment) or all(w.lower() in _NOISE_WORDS for w in words):
            continue
        if any(len(w) >= 3 for w in words):
            return " ".join(w.lower() for w in words)
    return None


def person_identity(txn: Transaction) -> Optional[tuple[Optional[str], Optional[str]]]:
    """
    (masked_vpa, name_token) when this transaction is with an individual:
    UPI-app rows the importer classified as peer payments, bank rows with a
    masked UPI ID (the browser masks only personal IDs; a remark like "Rent"
    may still have matched a normalizer pattern), or bank rows with no
    recognized merchant and a P2A (person-to-account) marker.
    """
    text = txn.merchant_raw or ""
    vpa_match = MASKED_VPA.search(text)
    is_peer = txn.transaction_nature in (TransactionNature.peer_payment_sent, TransactionNature.peer_payment_received)
    bank_peer = vpa_match or (not txn.merchant_clean and re.search(r"\bP2A\b", text))
    if not is_peer and not bank_peer:
        return None
    vpa = None
    if vpa_match:
        local, handle = vpa_match.group(0).split("@")
        vpa = f"{local.upper()}@{handle.lower()}"
    name = _name_token(text)
    if not vpa and not name:
        return None
    return vpa, name


def person_key(identity: tuple[Optional[str], Optional[str]]) -> str:
    vpa, name = identity
    return hashlib.sha256(f"{vpa or ''}|{name or ''}".encode()).hexdigest()
