"""
Bank alert emails → one normalized row, in memory.

Nothing here persists or logs email content. The caller
(api/routes/internal.py) stores only the normalized, PII-stripped row
(through the normal import pipeline) and metadata (bank, outcome, time).

UNVERIFIED: the per-bank templates follow publicly seen alert wording; real
alerts vary by bank, product and year. Anything the templates miss goes to
the generic parser; anything that still fails is counted, never stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from html import unescape
from typing import Optional

from app.core.alert_senders import GMAIL_FORWARDING_SENDER, bank_for_sender, sender_domain_ok
from app.services.pii import clean_reference, holder_name_pattern, sanitize_description, utr_from_upi_text

AMOUNT = r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{1,2})?)"
DEBIT_WORDS = re.compile(r"\b(debited|spent|sent|paid|withdrawn|withdrawal|purchase|charged|used)\b", re.I)
CREDIT_WORDS = re.compile(r"\b(credited|received|deposited|refund(?:ed)?|reversed)\b", re.I)
NOT_A_TRANSACTION = re.compile(r"\b(OTP|one[- ]time password|e-?statement|statement is ready|login|password)\b", re.I)
BALANCE_CONTEXT = re.compile(r"(bal(?:ance)?|limit|due|available|avl)[^.\n]{0,20}$", re.I)
CARD_PAYMENT = re.compile(r"payment\s+(?:of\s+)?.*\breceived\b|thank you for (?:the|your) payment|bill payment", re.I)


@dataclass
class Trust:
    bank: Optional[dict]
    reason: str          # "ok" | "unknown_sender" | "auth_failed"


@dataclass
class ParsedAlert:
    row: Optional[dict]      # ImportRow fields, or None
    outcome: str             # parsed | unparsed | not_transaction


# ── Sender trust ──────────────────────────────────────────────────────────────

def address_of(header: str) -> str:
    """Bare address from a From/To header ("HDFC Bank <alerts@hdfcbank.net>")."""
    m = re.search(r"<([^>]+)>", header or "")
    return (m.group(1) if m else (header or "")).strip().lower()


def auth_passes(auth_results: str) -> dict:
    """{"dkim": [domains that passed], "spf": [mailfrom domains that passed]} from Authentication-Results."""
    text = auth_results or ""
    dkim = [d.lower() for result, d in re.findall(r"dkim=(\w+)[^;]*?header\.[di]=@?([\w.-]+)", text, re.I) if result.lower() == "pass"]
    spf = [d.lower() for result, d in re.findall(r"spf=(\w+)[^;]*?smtp\.mailfrom=(?:[^@\s;]*@)?([\w.-]+)", text, re.I)
           if result.lower() == "pass"]
    return {"dkim": dkim, "spf": spf}


def check_sender(from_header: str, auth_results: str) -> Trust:
    """Allowlisted sender AND DKIM or SPF passing for that bank's own domain."""
    bank = bank_for_sender(address_of(from_header))
    if bank is None:
        return Trust(None, "unknown_sender")
    passed = auth_passes(auth_results)
    if any(sender_domain_ok(bank, d) for d in passed["dkim"] + passed["spf"]):
        return Trust(bank, "ok")
    return Trust(bank, "auth_failed")


# ── Gmail forwarding confirmation ─────────────────────────────────────────────

def gmail_confirmation(from_header: str, subject: str, text: str, auth_results: str) -> Optional[dict]:
    """{"link", "code"} if this is Gmail's (genuine) forwarding confirmation email."""
    if address_of(from_header) != GMAIL_FORWARDING_SENDER or "forwarding confirmation" not in (subject or "").lower():
        return None
    if not any(d == "google.com" or d.endswith(".google.com") for d in auth_passes(auth_results)["dkim"]):
        return None
    link = re.search(r"https://mail(?:-settings)?\.google\.com/mail/[^\s\"'<>]+", text or "")
    code = re.search(r"Confirmation code:\s*(\d{6,12})", text or "", re.I)
    if not link and not code:
        return None
    return {"link": link.group(0) if link else None, "code": code.group(1) if code else None}


# ── Parsing ───────────────────────────────────────────────────────────────────

def body_text(text: Optional[str], html: Optional[str]) -> str:
    if text and text.strip():
        return text
    stripped = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    stripped = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", stripped, flags=re.I)
    return unescape(re.sub(r"<[^>]+>", " ", stripped))


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATES = [
    (re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})[- ]?([A-Za-z]{3})[a-z]*[- ,]*(\d{2,4})\b"), "dMy"),
]
_TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\s*(AM|PM)?\b", re.I)


def find_date(text: str) -> Optional[date]:
    for pattern, kind in _DATES:
        for m in pattern.finditer(text):
            d, mo, y = m.groups()
            month = int(mo) if kind == "dmy" else _MONTHS.get(mo[:3].lower())
            if not month:
                continue
            year = int(y) + (2000 if len(y) == 2 else 0)
            try:
                return date(year, month, int(d))
            except ValueError:
                continue
    return None


def find_time(text: str) -> Optional[tuple[int, int, int]]:
    m = _TIME.search(text)
    if not m:
        return None
    h, mi, se, ampm = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0), (m.group(4) or "").upper()
    if ampm == "PM" and h < 12:
        h += 12
    if ampm == "AM" and h == 12:
        h = 0
    return h, mi, se


def find_amount(text: str) -> Optional[str]:
    """The first amount that isn't a balance or a limit."""
    for m in re.finditer(AMOUNT, text, re.I):
        if BALANCE_CONTEXT.search(text[max(0, m.start() - 30):m.start()]):
            continue
        value = m.group(1).replace(",", "")
        if re.fullmatch(r"\d+(\.\d{1,2})?", value) and float(value) > 0:
            whole, _, frac = value.partition(".")
            return f"{int(whole)}.{frac.ljust(2, '0')}"
    return None


def find_direction(text: str) -> Optional[str]:
    d, c = DEBIT_WORDS.search(text), CREDIT_WORDS.search(text)
    if d and c:
        return "debit" if d.start() < c.start() else "credit"
    return "debit" if d else "credit" if c else None


_MERCHANT = [
    re.compile(r"\bto\s+VPA\s+(\S+)\s+([A-Z][A-Za-z .&'-]{2,40}?)\s+on\b"),     # HDFC UPI: to VPA x@y NAME on
    re.compile(r"\bat\s+(.{2,60}?)\s+on\s+\d", re.I),                          # cards: at MERCHANT on 05-03-24
    re.compile(r"\b(?:to|towards)\s+(.{2,60}?)\s+on\s+\d", re.I),               # Kotak/SBI: to X on date
    re.compile(r"\bfrom\s+(.{2,60}?)\s+on\s+\d", re.I),                         # credits: from X on date
    re.compile(r"\bInfo[:\s-]+([^\n.]{2,80})", re.I),                           # ICICI: Info: UPI/…/MERCHANT
    re.compile(r"\b(?:at|to)\s+(UPI/\S+)", re.I),                               # Axis: at UPI/P2M/…/MERCHANT
    re.compile(r"\bfor\s+((?:NEFT|IMPS|RTGS)[^\n.]{2,60})", re.I),              # NEFT Cr-ACME…
    re.compile(r"\bby\s+([A-Za-z][^\n.]{2,60}?)\s*(?:\.|$)", re.I | re.M),
]


def find_merchant(text: str) -> Optional[str]:
    for pattern in _MERCHANT:
        m = pattern.search(text)
        if m:
            value = " ".join(g for g in m.groups() if g).strip(" .,:-")
            if value and not re.fullmatch(r"(your|a/?c|account|card)[\w\s/.*]*", value, re.I):
                return value[:120]
    return None


def find_reference(text: str) -> Optional[str]:
    m = re.search(r"(?:UPI\s*Ref(?:erence)?(?:\s*(?:No|number))?|Ref(?:erence)?\s*(?:No|number)|UTR(?:\s*No)?|RRN)\.?[:\s-]*([A-Za-z0-9]{6,})",
                  text, re.I)
    return clean_reference(m.group(1)) if m else clean_reference(utr_from_upi_text(text))


def find_last4(text: str) -> Optional[str]:
    m = re.search(r"(?:ending(?:\s+(?:in|with))?|[Xx*]{2,}|no\.?\s*[Xx*]*)\s*(\d{4})\b", text)
    return m.group(1) if m else None


# Bank templates: a match fills fields first; the generic finders fill the rest.
TEMPLATES: dict[str, list[re.Pattern]] = {
    "hdfc": [
        re.compile(r"Rs\.?\s*(?P<amount>[\d,.]+) has been (?P<dir>debited) from (?:account|a/c) \*\*(?P<last4>\d{4}) to VPA (?P<vpa>\S+) (?P<merchant>.+?) on (?P<date>\d{2}-\d{2}-\d{2,4})", re.I),
        re.compile(r"HDFC Bank (?P<card>Credit|Debit) Card ending (?P<last4>\d{4}) for Rs\.?\s*(?P<amount>[\d,.]+) at (?P<merchant>.+?) on (?P<date>\d{2}-\d{2}-\d{4})", re.I),
    ],
    "icici": [
        re.compile(r"(?:INR|Rs\.?)\s*(?P<amount>[\d,.]+) spent (?:using|on) ICICI Bank (?P<card>Credit|Debit)? ?Card XX(?P<last4>\d{4}) on (?P<date>\d{1,2}-[A-Za-z]{3}-\d{2,4}) on (?P<merchant>[^.]+)", re.I),
        re.compile(r"account XX(?P<last4>\d{3,4}) (?:has been|is) (?P<dir>debited|credited) with (?:INR|Rs\.?)\s*(?P<amount>[\d,.]+) on (?P<date>\d{1,2}-[A-Za-z]{3}-\d{2,4})", re.I),
    ],
    "sbi": [
        re.compile(r"A/C X+(?P<last4>\d{4}) (?:has been )?(?P<dir>debited|credited) by Rs\.?\s*(?P<amount>[\d,.]+) on (?P<date>\d{1,2}[A-Za-z]{3}\d{2,4})", re.I),
    ],
    "sbicard": [
        re.compile(r"Rs\.?\s*(?P<amount>[\d,.]+) spent on your SBI Credit Card ending (?P<last4>\d{4}) at (?P<merchant>.+?) on (?P<date>\d{2}/\d{2}/\d{2,4})", re.I),
    ],
    "axis": [
        re.compile(r"INR\s*(?P<amount>[\d,.]+) (?P<dir>debited|credited) (?:from|to) A/c no\. XX(?P<last4>\d{4}) on (?P<date>\d{2}-\d{2}-\d{4}) (?P<time>\d{2}:\d{2}:\d{2})", re.I),
        re.compile(r"INR\s*(?P<amount>[\d,.]+) spent on Axis Bank (?P<card>Credit|Debit) Card no\. XX(?P<last4>\d{4}) at (?P<merchant>.+?) on (?P<date>\d{2}-\d{2}-\d{2,4})", re.I),
    ],
    "kotak": [
        re.compile(r"(?P<dir>Sent|Received) Rs\.?\s*(?P<amount>[\d,.]+) (?:from|in your) Kotak Bank AC X(?P<last4>\d{4}) (?:to|from) (?P<merchant>\S+) on (?P<date>\d{2}-\d{2}-\d{2,4})", re.I),
    ],
}


def parse_alert(bank: dict, subject: str, text: str, received_at: datetime, holder_name: Optional[str] = None) -> ParsedAlert:
    body = f"{subject or ''}\n{text or ''}"
    fields: dict = {}
    for pattern in TEMPLATES.get(bank["key"], []):
        m = pattern.search(body)
        if m:
            fields = {k: v for k, v in m.groupdict().items() if v}
            break

    amount = find_amount(f"Rs {fields['amount']}") if fields.get("amount") else None
    amount = amount or find_amount(body)

    word = (fields.get("dir") or "").lower()
    if word in ("debited", "sent", "spent"):
        direction = "debit"
    elif word in ("credited", "received"):
        direction = "credit"
    elif fields.get("card"):
        direction = "debit"      # the card templates only match purchases ("…Card ending 4321 for Rs 2,199 at …")
    else:
        direction = find_direction(body)
    if not amount or not direction:
        transactional = DEBIT_WORDS.search(body) or CREDIT_WORDS.search(body)
        if NOT_A_TRANSACTION.search(body) or not transactional:
            return ParsedAlert(None, "not_transaction")
        return ParsedAlert(None, "unparsed")

    day = find_date(fields["date"]) if fields.get("date") else None
    day = day or find_date(body) or received_at.date()
    clock_time = find_time(fields.get("time") or body)
    stamp = f"{day.isoformat()}T{clock_time[0]:02d}:{clock_time[1]:02d}:{clock_time[2]:02d}" if clock_time else day.isoformat()

    merchant = " ".join(v for v in (fields.get("vpa"), fields.get("merchant")) if v) or find_merchant(body)
    is_card = bool(fields.get("card")) or bool(re.search(r"\bcredit card\b|\bdebit card\b|\bcard (?:ending|no|xx)", body, re.I))
    credit_card = bool(re.search(r"credit card", body, re.I)) or bank["key"] in ("sbicard", "amex")
    fallback = "Card payment" if is_card else "UPI payment" if re.search(r"\bUPI\b", body) else "Bank transfer"
    description = sanitize_description(merchant or fallback, name_pattern=holder_name_pattern(holder_name)) or fallback
    last4 = fields.get("last4") or find_last4(body)
    label = f"{bank['name']}{' Credit Card' if credit_card else ''}{f' x{last4[-4:]}' if last4 else ''}"
    bill_payment = credit_card and direction == "credit" and bool(CARD_PAYMENT.search(body))

    return ParsedAlert({
        "date": stamp, "description_raw": description, "amount": amount, "direction": direction,
        "reference": find_reference(body), "source_type": "email_alert", "source_label": label[:60],
        "type": "transfer" if bill_payment else "transaction",
    }, "parsed")
