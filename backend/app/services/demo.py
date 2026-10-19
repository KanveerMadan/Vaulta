"""
The shared, read-only demo account: four months of realistic Indian data,
dated relative to today so it always looks current. Rows go through the same
pipeline as a real user's (import_rows, manual entries, detection, review
answers), in the style of tests/test_end_to_end.py.

seed() deletes the demo user and rebuilds it (idempotent; one at a time via
an advisory lock). The hourly internal run reseeds once a day; the first
"Try the demo" seeds it if it doesn't exist yet.

Run by hand:  python -m app.services.demo
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from contextlib import contextmanager
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.database import engine
from app.core.demo import DEMO_UID
from app.core.scope import bind_user, find_user
from app.models.person import Person
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.imports import ImportRow
from app.schemas.transaction import ManualTransactionCreate, SplitPartIn, TransactionUpdate
from app.services import reports, transaction_service
from app.services.budgets import create_or_reactivate
from app.services.detection import run_detection
from app.services.goals import add_entry, create_goal
from app.services.people import set_tag
from app.services.recurring import add_months

logger = logging.getLogger(__name__)

# The prefix of signed demo tokens, not a secret
TOKEN_PREFIX = "demo."  # nosec B105
TOKEN_TTL_SECONDS = 2 * 3600
LOCK_ID = 74_219_001                   # pg advisory lock key for seeding
MONTHS = 4

# ── Session tokens: "demo.<session id>.<expiry>.<signature>", signed with SECRET_KEY ──


def _sign(payload: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"demo|{payload}".encode(), hashlib.sha256).hexdigest()


def new_token(now: Optional[float] = None) -> tuple[str, int]:
    expires = int((now or time.time()) + TOKEN_TTL_SECONDS)
    payload = f"{secrets.token_hex(8)}.{expires}"
    return f"{TOKEN_PREFIX}{payload}.{_sign(payload)}", TOKEN_TTL_SECONDS


def read_token(token: str) -> Optional[str]:
    """The demo session id if the token is genuine and unexpired, else None."""
    try:
        sid, expires, sig = token[len(TOKEN_PREFIX):].split(".")
        if int(expires) < time.time():
            return None
    except ValueError:
        return None
    return sid if hmac.compare_digest(sig, _sign(f"{sid}.{expires}")) else None


# ── Data ──────────────────────────────────────────────────────────────────────

def _row(day: date, desc: str, amount: str, direction: str = "debit", ref: Optional[str] = None,
         source: str = "bank_csv", label: str = "HDFC Bank", at: Optional[str] = None) -> ImportRow:
    return ImportRow(date=f"{day.isoformat()}T{at}" if at else day.isoformat(), description_raw=desc, amount=amount,
                     direction=direction, reference=ref, source_type=source, source_label=label)


def _rows(today: date) -> tuple[list[ImportRow], list[ImportRow], list[ImportRow], list[ImportRow]]:
    """(HDFC bank, SBI bank, HDFC credit card, Google Pay) for the last MONTHS months up to today."""
    hdfc, sbi, card, gpay = [], [], [], []
    first = today.replace(day=1)
    for k in range(MONTHS - 1, -1, -1):          # oldest month first
        m = add_months(first, -k)

        def d(day: int) -> Optional[date]:
            x = m.replace(day=min(day, 28))
            return x if x <= today else None

        def add(target, day, *args, **kw):
            if (x := d(day)) is not None:
                target.append(_row(x, *args, **kw))

        tag = f"{m:%y%m}"
        add(hdfc, 1, "NEFT CR-ACME CORP PAYROLL", "92000.00", "credit", ref=f"N{tag}ACME01")
        add(hdfc, 3, "UPI-RAHUL SHARMA-R***@okicici-XXXX-Rent", "25000.00", ref=f"6124{tag}0003")
        add(hdfc, 2, "UPI-CULTFIT-cultfit@hdfcbank-XXXX", "1500.00", ref=f"6124{tag}0002")
        add(hdfc, 5, "ACH D- ZERODHA MF SIP", "5000.00")
        add(hdfc, 4, "ATW-512345XXXXXX6789-S1ANMU12-BANGALORE", "2000.00")
        add(hdfc, 17, "ATW-512345XXXXXX6789-S1ANMU12-BANGALORE", "2000.00")
        add(hdfc, 20, "BILLPAY HDFC CC PAYMENT", "9000.00")
        add(card, 20, "PAYMENT RECEIVED - THANK YOU", "9000.00", "credit", source="credit_card", label="HDFC Bank Credit Card")
        for day, amt in ((5, "420.00"), (12, "380.00"), (19, "560.00"), (26, "310.00")):
            add(card, day, "SWIGGY BANGALORE", amt, source="credit_card", label="HDFC Bank Credit Card")
        add(card, 8, "NETFLIX COM", "499.00" if k >= 2 else "649.00", source="credit_card", label="HDFC Bank Credit Card")
        add(card, 11, "SPOTIFY INDIA", "119.00", source="credit_card", label="HDFC Bank Credit Card")
        for day, amt, n in ((9, "450.00", 1), (22, "390.00", 2)):
            add(gpay, day, "ZOMATO", amt, ref=f"6125{tag}{n:04d}", source="upi_google_pay", label="Google Pay")
        for day, amt, n in ((7, "640.00", 3), (15, "820.00", 4), (24, "510.00", 5)):
            add(gpay, day, "BLINKIT", amt, ref=f"6125{tag}{n:04d}", source="upi_google_pay", label="Google Pay")
        for day, desc, amt, n in ((6, "UBER INDIA", "240.00", 6), (14, "OLA", "180.00", 7), (21, "UBER INDIA", "310.00", 8)):
            add(gpay, day, desc, amt, ref=f"6125{tag}{n:04d}", source="upi_google_pay", label="Google Pay")
        add(sbi, 10, "BESCOM BILL PAYMENT", {3: "1350.00", 2: "1420.00", 1: "1280.00", 0: "1310.00"}[k], label="SBI")
        if k == 2:
            add(hdfc, 18, "IMPS-SELF-SBI", "10000.00")
            add(sbi, 18, "IMPS CR FROM HDFC SELF", "10000.00", "credit", label="SBI")
            add(hdfc, 12, "UPI/P2A/XXXX/ANKIT JAIN/loan", "3000.00")
        if k == 1:
            add(hdfc, 2, "UPI/P2A/XXXX/ANKIT JAIN/return", "3000.00", "credit")
            add(card, 10, "AMAZON PAY INDIA", "2499.00", source="credit_card", label="HDFC Bank Credit Card")
            add(card, 16, "AMAZON PAY INDIA REFUND", "899.00", "credit", source="credit_card", label="HDFC Bank Credit Card")
            add(card, 13, "DMART BANGALORE", "3200.00", source="credit_card", label="HDFC Bank Credit Card")
    # Recent things worth an alert: a failed UPI never reversed, a double charge, an unusually big order
    gpay.append(_row(today - timedelta(days=3), "ZOMATO FAILED", "349.00", ref="612599990001", source="upi_google_pay", label="Google Pay"))
    for n, at in ((2, "13:02:00"), (3, "13:06:00")):
        gpay.append(_row(today - timedelta(days=2), "BLINKIT", "455.00", ref=f"61259999000{n}", source="upi_google_pay",
                         label="Google Pay", at=at))
    card.append(_row(today - timedelta(days=1), "SWIGGY BANGALORE", "1850.00", source="credit_card", label="HDFC Bank Credit Card"))
    return hdfc, sbi, card, gpay


CASH_SPENDS = (("Auto", "Transport", "150"), ("Vegetables", "Groceries", "300"), ("Chai", "Food & Dining", "60"),
               ("Tailor", "Shopping", "400"))
BUDGETS = ((None, "70000"), ("Food & Dining", "6000"), ("Shopping", "5000"), ("Transport", "2500"), ("Groceries", "4000"))


def _find(db: Session, user: User, needle: str, on: Optional[date] = None) -> Optional[Transaction]:
    q = db.query(Transaction).filter(Transaction.user_id == user.id)    # merchant_raw is encrypted: compare here
    rows = [t for t in q if t.merchant_raw == needle and (on is None or t.transaction_date.date() == on)]
    return rows[0] if rows else None


@contextmanager
def _seed_lock():
    """One seeder at a time, held for the whole rebuild (on its own connection; seeding commits many times)."""
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_ID})
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_ID})


def seed(db: Session, today: Optional[date] = None) -> User:
    """Delete and rebuild the demo user. Returns it."""
    with _seed_lock():
        return _seed(db, today or clock.today())


def _seed(db: Session, today: date) -> User:
    old = find_user(db, "firebase_uid", DEMO_UID)
    if old:
        db.delete(old)
        db.flush()
    user = User(firebase_uid=DEMO_UID, email="demo@vaulta.invalid", full_name="Demo",
                email_weekly=False, email_monthly=False, email_annual=False, telegram_weekly=False,
                onboarding={"status": "done", "step": "finish", "basics_done": True, "banks": ["hdfc", "sbi"],
                            "upi_apps": ["Google Pay"], "income": "92000", "payday": 1},
                alert_prefs={t: {"telegram": False, "email": False} for t in
                             ("budget_threshold", "duplicate_charge", "failed_upi_unreversed", "renewal_tomorrow",
                              "price_change", "salary_received", "unusual_amount")})
    bind_user(db, user)
    db.add(user)
    db.commit()

    for statement in _rows(today):
        if statement:
            transaction_service.import_rows(db, user, statement)

    first = today.replace(day=1)
    for k in range(MONTHS - 1, -1, -1):
        m = add_months(first, -k)
        for i, (merchant, category, amount) in enumerate(CASH_SPENDS):
            day = m.replace(day=min(6 + i * 5, 28))
            if day <= today:
                transaction_service.create_manual_transaction(db, user, ManualTransactionCreate(
                    client_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"demo|{day}|{merchant}")), date=day.isoformat(),
                    amount=amount, merchant=merchant, category=category, payment_method="cash"))

    # The user's own answers: the rent payee, the loan, the split
    rent = db.query(Person).filter(Person.user_id == user.id).all()
    for p in rent:
        if "rahul" in p.display_name.lower():
            set_tag(p, "Rent")
    db.commit()
    if loan := _find(db, user, "UPI/P2A/XXXX/ANKIT JAIN/loan"):
        transaction_service.update_transaction(db, loan, TransactionUpdate(kind="lent"))
    if back := _find(db, user, "UPI/P2A/XXXX/ANKIT JAIN/return"):
        transaction_service.update_transaction(db, back, TransactionUpdate(kind="repayment"))
    if dmart := _find(db, user, "DMART BANGALORE"):
        transaction_service.split_transaction(db, dmart, [SplitPartIn(amount="2000", category="Groceries"),
                                                           SplitPartIn(amount="1200", category="Shopping")])

    for category, limit in BUDGETS:
        create_or_reactivate(db, user, category, Decimal(limit))
    goal = create_goal(db, user, "Goa trip", Decimal("40000"), add_months(today, 5), "Food & Dining")
    for k, amount in ((2, "5000"), (1, "5000"), (0, "3000")):
        add_entry(db, goal, Decimal(amount), min(add_months(first, -k).replace(day=2), today))

    run_detection(db, user, today)                       # budgets/answers in place: alerts for this month
    for k in (3, 2, 1):
        reports.generate(db, user.id, "monthly", add_months(first, -k))
    reports.generate(db, user.id, "weekly", reports.last_complete("weekly", today))
    user.onboarding = {**user.onboarding, "demo_seeded": today.isoformat()}   # complete: visitors waiting on the lock now see it
    db.commit()
    logger.info(f"demo: seeded for {today}")
    return user


def demo_user(db: Session) -> Optional[User]:
    return find_user(db, "firebase_uid", DEMO_UID)


def ensure_fresh(db: Session, today: Optional[date] = None, create: bool = False) -> Optional[User]:
    """
    Hourly run (create=False): rebuild when last built on an earlier day; never create it.
    A visitor (create=True): build it only if there is no complete one — never make a
    visitor wait for the daily rebuild, but do wait for a build that's still running
    (the landing page's live preview starts one), so nobody gets a half-built demo.
    """
    today = today or clock.today()
    fresh = lambda u: u is not None and (u.onboarding or {}).get("demo_seeded") == today.isoformat()
    complete = lambda u: u is not None and "demo_seeded" in (u.onboarding or {})
    user = demo_user(db)
    if fresh(user) or (user is None and not create) or (create and complete(user)):
        return user
    with _seed_lock():
        db.expire_all()
        user = demo_user(db)       # another request may have built it while we waited
        return user if fresh(user) or (create and complete(user)) else _seed(db, today)


if __name__ == "__main__":
    from app.core.database import SessionLocal
    with SessionLocal() as session:
        u = seed(session)
        print(f"demo user {u.id} seeded at {datetime.now(timezone.utc).isoformat()}")
