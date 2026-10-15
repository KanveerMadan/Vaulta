"""
Quick-add parser for the Telegram bot: "150 auto cash", "1.2k groceries dmart
yesterday". Port of frontend/src/lib/quickAdd.js — same rules, kept in parity
by fixtures/quick_add_cases.json (both test suites run it).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

KEYWORDS = {
    "Transport": ["auto", "rickshaw", "cab", "taxi", "uber", "ola", "rapido", "metro", "bus", "train", "petrol", "diesel", "fuel", "parking", "toll"],
    "Groceries": ["grocery", "groceries", "vegetables", "veggies", "fruits", "milk", "kirana", "dmart", "bigbasket", "blinkit", "zepto", "instamart"],
    "Food & Dining": ["food", "lunch", "dinner", "breakfast", "snacks", "chai", "tea", "coffee", "restaurant", "swiggy", "zomato", "pizza", "biryani"],
    "Shopping": ["shopping", "clothes", "shoes", "amazon", "flipkart", "myntra", "gift"],
    "Utilities": ["electricity", "water", "gas", "wifi", "internet", "broadband", "recharge", "mobile", "bill"],
    "Rent & Housing": ["rent", "maintenance", "society", "maid", "plumber", "electrician"],
    "Health": ["medicine", "medicines", "pharmacy", "doctor", "hospital", "clinic", "chemist"],
    "Entertainment": ["movie", "movies", "netflix", "spotify", "concert", "game"],
    "Travel": ["flight", "hotel", "trip", "irctc", "holiday"],
    "Education": ["books", "course", "tuition", "fees", "school", "college"],
}
GENERIC = {
    "grocery", "groceries", "vegetables", "veggies", "fruits", "milk", "food", "lunch", "dinner", "breakfast",
    "snacks", "shopping", "clothes", "shoes", "gift", "electricity", "water", "gas", "wifi", "internet",
    "broadband", "recharge", "mobile", "bill", "rent", "maintenance", "medicine", "medicines", "doctor",
    "movie", "movies", "flight", "hotel", "trip", "holiday", "books", "course", "tuition", "fees",
    "petrol", "diesel", "fuel", "parking", "toll",
}
PAYMENT_WORDS = {"cash": "cash", "upi": "online", "card": "online", "online": "online", "gpay": "online",
                 "phonepe": "online", "paytm": "online", "netbanking": "online"}
INCOME_WORDS = {"received", "got", "salary", "income", "refund", "credited"}
FILLER = {"for", "on", "at", "to", "from", "paid", "spent", "rs", "inr", "via", "by", "the", "a"}
WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]   # JS getDay order
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MULTIPLIERS = {"k": 1000, "l": 100000, "c": 10000000}


def guess_category(words: list[str]) -> Optional[str]:
    for w in words:
        for category, keywords in KEYWORDS.items():
            if w in keywords:
                return category
    return None


def _day_month(day: int, month: int, today: date) -> Optional[date]:
    try:
        d = date(today.year, month, day)
    except ValueError:
        return None
    return d.replace(year=today.year - 1) if d > today else d


def _js_weekday(d: date) -> int:
    return (d.weekday() + 1) % 7


def parse_quick_add(text: str, today: date) -> Optional[dict]:
    """{amount, merchant, category, date, payment_method, direction}, or None without an amount."""
    rest = f" {text.lower().strip()} "
    found = {"date": today}

    def take(pattern: str, fn) -> None:
        nonlocal rest
        m = re.search(pattern, rest)
        if not m:
            return
        d = fn(m)
        if d:
            found["date"] = d
        rest = rest[:m.start()] + " " + rest[m.end():]

    months = "|".join(MONTHS)
    take(r"\bday before yesterday\b", lambda m: today - timedelta(days=2))
    take(r"\byesterday\b", lambda m: today - timedelta(days=1))
    take(r"\btoday\b", lambda m: today)
    take(rf"\b(?:last\s+)?({'|'.join(WEEKDAYS)})\b",
         lambda m: today - timedelta(days=((_js_weekday(today) - WEEKDAYS.index(m.group(1))) + 7) % 7 or 7))
    take(r"\b(\d{1,2})[/-](\d{1,2})\b(?![/-]?\d)", lambda m: _day_month(int(m.group(1)), int(m.group(2)), today))
    take(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*({months})[a-z]*\b",
         lambda m: _day_month(int(m.group(1)), MONTHS.index(m.group(2)) + 1, today))
    take(rf"\b({months})[a-z]*\s+(\d{{1,2}})(?:st|nd|rd|th)?\b",
         lambda m: _day_month(int(m.group(2)), MONTHS.index(m.group(1)) + 1, today))

    m = re.search(r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|lakhs?|lacs?|l|crores?|cr)?\b", rest)
    if not m:
        return None
    multiplier = MULTIPLIERS.get((m.group(2) or " ")[0], 1)
    amount = (Decimal(m.group(1).replace(",", "")) * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        return None
    rest = rest.replace(m.group(0), " ", 1)

    words = [w for w in rest.split() if w not in FILLER]
    payment_method, direction, category = "cash", "debit", None
    named, generic = [], []
    for w in words:
        if w in PAYMENT_WORDS:
            payment_method = PAYMENT_WORDS[w]
            continue
        if w in INCOME_WORDS:
            direction = "credit"
        category = category or guess_category([w])
        (generic if w in GENERIC or w in INCOME_WORDS else named).append(w)
    merchant = re.sub(r"\b\w", lambda c: c.group(0).upper(), " ".join(named or generic)) or "Cash spend"

    return {
        "amount": str(int(amount)) if amount == amount.to_integral() else f"{amount:.2f}",
        "merchant": merchant,
        "category": category,
        "date": found["date"].isoformat(),
        "payment_method": payment_method,
        "direction": direction,
    }
