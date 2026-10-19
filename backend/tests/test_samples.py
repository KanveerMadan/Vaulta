"""
The preview layer (core/samples.py): sample rows never change a number anywhere. The guard test takes three months of
real data, records what every service says, adds sample rows of every kind through the real import pipeline, re-runs
detection, and requires every answer to be identical. A new service that reads transactions some other way fails it.
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone

from app.core import clock
from app.models.alert import Alert
from app.models.anomaly import Anomaly
from app.models.person import Person
from app.models.recurring import RecurringSeries
from app.models.transaction import Transaction
from app.schemas.imports import ImportRow
from app.services import (analytics, cash, categorizer, coverage, export, getting_started, recategorise, reports,
                          samples, transaction_service)
from app.services.chat_tools import READ_TOOLS
from app.services.detection import run_detection
from app.services.review import build_cards
from tests.conftest import user_session
from tests.test_end_to_end import TODAY, USER, frozen_today, load_three_months  # noqa: F401  (fixture)

APRIL, JUNE_1, JUNE_30 = date(2024, 4, 1), date(2024, 6, 1), date(2024, 6, 30)
CHAT = {
    "spend_summary": {"start": "2024-04-01", "end": "2024-06-30", "group_by": "category"},
    "top_merchants": {"start": "2024-04-01", "end": "2024-06-30"},
    "compare_periods": {"a_start": "2024-06-01", "a_end": "2024-06-30", "b_start": "2024-05-01", "b_end": "2024-05-31"},
    "budget_status": {"month": "2024-06"}, "recurring_overview": {}, "upcoming": {"days": 14}, "person_balances": {},
    "income_summary": {"start": "2024-04-01", "end": "2024-06-30"}, "savings_rate": {"start": "2024-04-01", "end": "2024-06-30"},
    "forecast_month_end": {"month": "2024-06"}, "safe_to_spend_today": {}, "cash_wallet": {}, "goal_status": {},
    "search_transactions": {"limit": 50}, "what_if_reduce": {"category_or_merchant": "Food & Dining", "percent": 20},
}


def everything(db, user) -> str:
    out = {f"spend:{g}": analytics.spend_summary(db, user.id, APRIL, JUNE_30, g)
           for g in ("category", "subcategory", "tag", "merchant", "person", "day", "week", "month")}
    out.update({
        "income": analytics.income_summary(db, user.id, APRIL, JUNE_30),
        "savings": analytics.savings_rate(db, user.id, APRIL, JUNE_30),
        "budgets": analytics.budget_status(db, user.id, TODAY),
        "forecast": analytics.forecast_month_end(db, user.id, TODAY),
        "outlook": analytics.month_outlook(db, user.id, TODAY),
        "safe": analytics.safe_to_spend_today(db, user.id),
        "recurring": analytics.recurring_overview(db, user.id),
        "upcoming": analytics.upcoming(db, user.id, 14),
        "people": analytics.person_balances(db, user.id),
        "goals": analytics.goals_overview(db, user.id),
        "top": analytics.top_merchants(db, user.id, APRIL, JUNE_30),
        "compare": analytics.compare_periods(db, user.id, JUNE_1, JUNE_30, date(2024, 5, 1), date(2024, 5, 31)),
        "wallet": cash.wallet(db, user.id),
        "coverage": coverage.sources(db, user),
        "cards": sorted(c.id for c in build_cards(db, user)),
        "report": reports.build_report(db, user.id, "monthly", JUNE_1),
        "checklist": getting_started.checklist(db, user, True),
        "memory": categorizer.load_memory(db, user.id),
        "recategorise": len(recategorise.plan(db, user)),
        "export": {table: len(rows) for table, rows in export.collect(db, user).items()},
        "anomalies": sorted((a.type, str(a.occurred_on)) for a in db.query(Anomaly).filter(Anomaly.user_id == user.id)),
        "alerts": sorted(a.dedup_key for a in db.query(Alert).filter(Alert.user_id == user.id)),
        "people_rows": sorted(p.display_name for p in db.query(Person).filter(Person.user_id == user.id)),
        "series": sorted(s.display_name for s in db.query(RecurringSeries).filter(RecurringSeries.user_id == user.id)),
        "chat": {tool: READ_TOOLS[tool](db, user, args) for tool, args in CHAT.items()},
        "transactions": sorted((str(t.id), t.kind.value, t.category, t.subcategory, str(t.refund_of_id), str(t.person_id),
                                str(t.transfer_group_id), t.cash_flow) for t in db.query(Transaction).filter(Transaction.user_id == user.id)),
    })
    db.rollback()
    return json.dumps(out, default=str, sort_keys=True)


def sample_rows() -> list[ImportRow]:
    """One of everything a sample could be mistaken for: spending, salary, a refund, a person, ATM cash, a transfer,
    an unusual amount, a duplicate charge, a recurring-looking payment and a known merchant."""
    def r(d, desc, amount, direction="debit", type_="transaction", source="bank_csv"):
        return ImportRow(date=d, description_raw=desc, amount=amount, direction=direction, reference=None,
                         source_type=source, source_label="HDFC Bank", type=type_)
    return [
        r("2024-06-27", "UPI-SWIGGY-swiggy@ybl-Payment", "999.00"),
        r("2024-06-27", "UPI-SWIGGY-swiggy@ybl-Payment", "999.00"),
        r("2024-06-28", "NEFT CR-ACME CORP PAYROLL-SAL", "90000.00", "credit"),
        r("2024-06-28", "REFUND SWIGGY ORDER", "450.00", "credit"),
        r("2024-06-26", "UPI-RAVI KUMAR-R***@okaxis-Rent", "20000.00"),
        r("2024-06-25", "ATW-512345XXXXXX6789-S1ANMU12-BANGALORE", "5000.00"),
        r("2024-06-25", "SELF TRANSFER TO OWN A/C", "15000.00", type_="transfer"),
        r("2024-06-24", "POS AMAZON SELLER SERVICES BANGALORE", "48000.00"),
        r("2024-06-03", "NETFLIX COM", "649.00"),
        r("2024-06-20", "Zomato", "300.00", source="upi_google_pay"),
    ]


def test_samples_change_nothing_anywhere(client):
    load_three_months(client)
    with user_session("rahul") as (db, user):
        run_detection(db, user, TODAY)
        before = everything(db, user)
        transaction_service.import_rows(db, user, sample_rows(), simulation_id=uuid.uuid4())
        run_detection(db, user, TODAY)
        assert samples.count(db, user) == len(sample_rows())
        after = everything(db, user)
    assert after == before


def test_samples_are_listed_labelled_but_not_editable_and_never_merge(client):
    load_three_months(client)
    real_before = {t["id"] for t in client.get("/api/transactions?page_size=200", headers=USER).json()["items"]}
    with user_session("rahul") as (db, user):
        # the same row as a real one: a sample never merges into it (nor it into the sample)
        transaction_service.import_rows(db, user, [ImportRow(date="2024-06-03", description_raw="NETFLIX COM", amount="649.00",
                                                             direction="debit", source_type="bank_csv", source_label="HDFC Bank")],
                                        simulation_id=uuid.uuid4())
    items = client.get("/api/transactions?page_size=200", headers=USER).json()["items"]
    sample = [t for t in items if t["is_sample"]]
    assert len(sample) == 1 and {t["id"] for t in items if not t["is_sample"]} == real_before
    sid = sample[0]["id"]
    assert client.patch(f"/api/transactions/{sid}", json={"category": "Travel"}, headers=USER).status_code == 404
    assert client.get(f"/api/transactions/{sid}/explanation", headers=USER).status_code == 404
    assert client.get("/api/simulations", headers=USER).json() == {"samples": 1}


def test_clear_and_auto_delete_after_an_hour(client, monkeypatch):
    load_three_months(client)
    with user_session("rahul") as (db, user):
        transaction_service.import_rows(db, user, sample_rows()[:3], simulation_id=uuid.uuid4())
    assert client.get("/api/simulations", headers=USER).json() == {"samples": 3}
    real_now, later = clock.now, datetime.now(timezone.utc) + timedelta(minutes=61)
    monkeypatch.setattr(clock, "now", lambda: later)
    assert client.get("/api/simulations", headers=USER).json() == {"samples": 0}     # gone after an hour
    monkeypatch.setattr(clock, "now", real_now)
    with user_session("rahul") as (db, user):
        transaction_service.import_rows(db, user, sample_rows()[:2], simulation_id=uuid.uuid4())
    assert client.delete("/api/simulations", headers=USER).json() == {"cleared": 2}
    assert client.get("/api/simulations", headers=USER).json() == {"samples": 0}


def test_the_hourly_run_deletes_expired_samples(client, monkeypatch):
    load_three_months(client)
    with user_session("rahul") as (db, user):
        transaction_service.import_rows(db, user, sample_rows()[:2], simulation_id=uuid.uuid4())
    from app.services import scheduler
    from tests.conftest import SessionLocal
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    monkeypatch.setattr(clock, "now", lambda: later)
    with SessionLocal() as db:
        assert scheduler.run(db, later)["samples_purged"] == 2


def test_samples_are_per_user(client):
    from tests.conftest import as_user
    bob = as_user("bob")
    load_three_months(client)
    with user_session("rahul") as (db, user):
        transaction_service.import_rows(db, user, sample_rows()[:2], simulation_id=uuid.uuid4())
    assert client.get("/api/simulations", headers=bob).json() == {"samples": 0}
    assert client.delete("/api/simulations", headers=bob).json() == {"cleared": 0}
    assert client.get("/api/simulations", headers=USER).json() == {"samples": 2}
