"""
PII stripping on the server, for rows that don't come through the browser
(bank alert emails). Port of frontend/src/import/pii.js — same rules, kept in
parity by fixtures/pii_cases.json, which both test suites run (and
tests/test_pii.py checks the merchant-VPA token list matches pii.js).

  personal UPI IDs → "R***@okaxis"; phone numbers → "XXXXXXXX10";
  IFSC codes → removed; 9+ digit runs → "XXXX"; references kept only if they
  look like a transaction id; the holder's own whole name → "SELF".
"""

from __future__ import annotations

import re
from typing import Optional

BUSINESS_VPA_TOKENS = [
    # payment gateways / merchant QR
    "paytmqr", "bharatpe", "razorpay", "rzp", "cashfree", "payu", "billdesk", "pinelabs", "mswipe",
    "instamojo", "ccavenue", "juspay", "easebuzz", "merchant", "phonepemerchant", "gpaymerchant",
    # large merchants that collect on their own VPA
    "swiggy", "zomato", "zepto", "blinkit", "bigbasket", "amazon", "amazonpay", "flipkart", "myntra",
    "irctc", "uber", "ola", "rapido", "airtel", "jio", "netflix", "spotify", "bookmyshow", "dmart",
    "nykaa", "meesho", "dunzo", "tataplay", "bescom", "lic",
]

LETTER = r"[^\W\d_]"
# "-" is excluded from the local part: it is the field separator in bank narrations
VPA = re.compile(r"([a-zA-Z0-9._]{2,256})@([a-zA-Z][a-zA-Z0-9.]{1,64})")
PHONE = re.compile(r"(?<![\dX])(?:\+?91[\s-]?)?([6-9]\d{9})(?!\d)")
IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
LONG_DIGITS = re.compile(r"\d{9,}")
UTR_IN_UPI = re.compile(r"(?<!\d)(\d{12})(?!\d)")


def is_business_vpa(vpa: str) -> bool:
    tokens = re.split(r"[.\-_@]", vpa.lower())
    return any(t == b or (len(b) >= 5 and t.startswith(b)) for t in tokens for b in BUSINESS_VPA_TOKENS)


def mask_vpa(local: str, handle: str) -> str:
    first = local[0].upper() if local[0].isalpha() else "X"
    return f"{first}***@{handle}"


def clean_reference(ref: Optional[str]) -> Optional[str]:
    """Keep a reference only if it looks like a transaction id, not an account number."""
    if not ref:
        return None
    s = str(ref).strip()
    if not re.fullmatch(r"[A-Za-z0-9/-]{3,40}", s):
        return None
    numeric = re.fullmatch(r"(?:[A-Za-z]{2,5}[-/]?)?0*(\d+)", s)
    if not numeric:
        return s
    digits = numeric.group(1)
    if len(digits) == 12:
        return digits
    if len(digits) <= 8:
        return s
    return s if re.search(r"[A-Za-z]", s) else None


def holder_name_pattern(display_name: Optional[str]) -> Optional[re.Pattern]:
    """The holder's whole name only (see pii.js holderNamePattern)."""
    tokens = [t for t in re.split(r"\s+", display_name or "") if re.fullmatch(f"{LETTER}{{2,}}", t)]
    if len(tokens) < 2:
        return None
    first, last = re.escape(tokens[0]), re.escape(tokens[-1])
    initial = re.escape(tokens[0][0])
    between = rf"(?:\s+{LETTER}+\.?){{0,2}}\s+"
    alternatives = [
        f"{first}{between}{last}", f"{last}{between}{first}",
        rf"{first}\s+{last}", rf"{last}\s+{first}",
        rf"{initial}(?:\.\s*|\s+){last}", rf"{last}\s+{initial}\.?",
    ]
    return re.compile(rf"(?<!{LETTER})(?:{'|'.join(alternatives)})(?!{LETTER})", re.IGNORECASE)


def sanitize_description(text: Optional[str], counts: Optional[dict] = None, name_pattern: Optional[re.Pattern] = None) -> str:
    counts = counts if counts is not None else {}

    def bump(k: str) -> None:
        counts[k] = counts.get(k, 0) + 1

    s = str(text or "")
    if name_pattern:
        before = s
        s = re.sub(r"\bSELF(?:\s+SELF)+\b", "SELF", name_pattern.sub("SELF", s))
        if s != before:
            bump("holder_name")

    def vpa(m: re.Match) -> str:
        if is_business_vpa(m.group(0)):
            return m.group(0)
        bump("upi_ids")
        return mask_vpa(m.group(1), m.group(2))

    def phone(m: re.Match) -> str:
        bump("phone_numbers")
        return f"XXXXXXXX{m.group(1)[-2:]}"

    def ifsc(m: re.Match) -> str:
        bump("ifsc_codes")
        return ""

    def digits(m: re.Match) -> str:
        bump("account_numbers")
        return "XXXX"

    s = VPA.sub(vpa, s)
    s = PHONE.sub(phone, s)
    s = IFSC.sub(ifsc, s)
    s = LONG_DIGITS.sub(digits, s)
    s = re.sub(r"[-/][\s/-]*(?=[-/])", "", s)
    return re.sub(r"\s+", " ", s).strip()[:200]


def utr_from_upi_text(text: str) -> Optional[str]:
    """A 12-digit UTR inside a UPI narration (same rule as sanitizeRows in pii.js)."""
    if not re.search(r"\bUPI\b|UPI[/-]", text or "", re.IGNORECASE):
        return None
    m = UTR_IN_UPI.search(text)
    return m.group(1) if m else None
