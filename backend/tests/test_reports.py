"""Reports on the Phase 2 end-to-end fixture (today = 2024-06-28)."""

from datetime import date

import pytest

from app.core.database import SessionLocal
from app.models.report import Report
from app.models.user import User
from app.services import llm
from app.services import reports as reports_service
from tests.conftest import as_user, user_session
from tests.test_end_to_end import USER, frozen_today, load_three_months  # noqa: F401 (fixture)

BOB = as_user("bob")


@pytest.fixture
def no_llm(monkeypatch):
    def unavailable(*a, **k):
        raise llm.LLMError("not configured")
    monkeypatch.setattr(llm, "complete", unavailable)


def gen(client, period_type, day, headers=USER):
    res = client.post("/api/reports/generate", json={"period_type": period_type, "date": day}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_monthly_report_numbers(client, no_llm):
    load_three_months(client)
    may = gen(client, "monthly", "2024-05-15")
    d = may["data"]
    assert (may["period_start"], may["period_end"], may["label"]) == ("2024-05-01", "2024-05-31", "May 2024")
    assert d["totals"] == {"spend": "24099.00", "income": "80000.00", "saved": "55901.00", "savings_rate_pct": "69.9", "transactions": 5}
    assert d["previous"] == {"start": "2024-04-01", "end": "2024-04-30", "spend": "23199.00", "income": "80000.00",
                             "spend_change": "900.00", "spend_change_pct": "3.9"}
    assert [(c["name"], c["amount"]) for c in d["top_categories"]] == [
        ("Rent & Housing", "20000.00"), ("Groceries", "1500.00"), ("Utilities", "1300.00"),
        ("Food & Dining", "800.00"), ("Entertainment", "499.00")]
    assert [(m["name"], m["amount"]) for m in d["top_merchants"]] == [
        ("Rent", "20000.00"), ("Zepto", "1500.00"), ("Electricity Bill", "1300.00"), ("Swiggy", "800.00"), ("Netflix", "499.00")]
    assert d["recurring"] == {"new": [], "cancelled": [], "price_changed": []}
    assert d["anomalies"] == []                                   # history starts in April: no trailing window yet
    assert d["people"] == {"owed_to_you": [{"name": "Ankit Jain", "amount": "1000.00", "days": 77}], "you_owe": []}
    # June allowance: May's income 80000 − 21899 recurring = 58101 → 1936.70/day × 30 days
    assert d["safe_to_spend_next"] == {"start": "2024-06-01", "end": "2024-06-30", "basis": "last month's income",
                                       "monthly_limit": "80000.00", "recurring_committed": "21899.00",
                                       "per_day": "1936.70", "amount": "58101.00"}
    assert d["budget"]["overall"] is None and d["budget"]["categories"] == []
    assert may["narrative_source"] == "template"
    assert may["narrative"].splitlines()[0] == "May 2024: you spent ₹24,099 and received ₹80,000."
    assert may["narrative"].splitlines()[-1].startswith("Suggestion:")


def test_june_recurring_changes(client, no_llm):
    load_three_months(client)
    jun = gen(client, "monthly", "2024-06-01")["data"]
    assert sorted(s["name"] for s in jun["recurring"]["new"]) == ["Electricity Bill", "Netflix", "Ravi Kumar"]
    assert jun["recurring"]["price_changed"] == [{"name": "Netflix", "amount": "649.00", "cadence": "monthly", "old_amount": "499.00"}]


def test_weekly_report(client, no_llm):
    load_three_months(client)
    wk = gen(client, "weekly", "2024-06-20")
    assert (wk["period_start"], wk["period_end"]) == ("2024-06-17", "2024-06-23")     # Monday–Sunday
    d = wk["data"]
    assert (d["totals"]["spend"], d["totals"]["transactions"]) == ("3000.00", 2)      # the Amazon split's two parts
    assert (d["previous"]["spend"], d["previous"]["spend_change"], d["previous"]["spend_change_pct"]) == ("949.00", "2051.00", "216.1")


def test_annual_wrapped(client, no_llm):
    load_three_months(client)
    w = gen(client, "annual", "2024-03-01")["data"]["wrapped"]
    assert w == {
        "top_merchant_by_visits": {"name": "Rent", "visits": 3},           # 5 merchants tie at 3; most spend wins
        "top_merchant_by_spend": {"name": "Rent", "amount": "60000.00"},
        "most_expensive_month": {"month": "2024-06", "amount": "25599.00"},
        "subscriptions_total": "1647.00",                                  # Netflix 499 + 499 + 649
        "biggest_category_change": {"category": "Rent & Housing", "this_year": "60000.00", "last_year": "0.00", "change": "60000.00"},
        "transaction_count": 34,
        "savings_rate_pct": "69.8",                                        # (241500 − 72897) / 241500
    }


def test_narrative_must_only_use_numbers_from_the_report(client, monkeypatch):
    load_three_months(client)
    with user_session("rahul") as (db, _user):
        uid = _user.id
        data = reports_service.build_report(db, uid, "monthly", date(2024, 5, 1))
    good = ("You spent ₹24,099 in May 2024, up ₹900 (3.9%) on April. Rent was ₹20,000.\n"
            "You saved 69.9% of ₹80,000.\nSuggestion: Zepto took ₹1,500; plan one weekly grocery order.")
    invented = good.replace("₹1,500", "₹1,600")
    rounded = good.replace("₹24,099", "about ₹24,000")
    assert reports_service.narrative_is_grounded(good, data)
    assert not reports_service.narrative_is_grounded(invented, data)
    assert not reports_service.narrative_is_grounded(rounded, data)

    monkeypatch.setattr(llm, "complete", lambda *a, **k: {"content": invented})
    may = gen(client, "monthly", "2024-05-01")
    assert (may["narrative_source"], may["narrative"].splitlines()[0]) == ("template", "May 2024: you spent ₹24,099 and received ₹80,000.")
    monkeypatch.setattr(llm, "complete", lambda *a, **k: {"content": good})
    apr_payload = {}

    def capture(messages, *a, **k):
        apr_payload["messages"] = messages
        return {"content": good.replace("₹24,099", "₹23,199").replace("up ₹900 (3.9%) on April", "in total")
                .replace("May 2024", "April 2024").replace("69.9", "71.0").replace("₹1,500", "₹900")}
    monkeypatch.setattr(llm, "complete", capture)
    apr = gen(client, "monthly", "2024-04-01")
    assert apr["narrative_source"] == "llm"
    sent = apr_payload["messages"][1]["content"]
    for private in ("UPI-RAVI KUMAR-R***@okaxis-XXXX-Rent", "R***@okaxis", "612400000408", "NEFT CR-ACME CORP PAYROLL"):
        assert private not in sent


def test_reports_are_idempotent_and_per_user(client, no_llm):
    load_three_months(client)
    a = gen(client, "monthly", "2024-05-01")
    b = gen(client, "monthly", "2024-05-31")
    assert a["id"] == b["id"]
    with SessionLocal() as db:
        assert db.query(Report).count() == 1
    archive = client.get("/api/reports", headers=USER).json()
    assert [(r["period_type"], r["label"], r["spend"]) for r in archive] == [("monthly", "May 2024", "24099.00")]
    assert client.get(f"/api/reports/{a['id']}", headers=USER).json()["data"]["totals"]["spend"] == "24099.00"
    assert client.get("/api/reports", headers=BOB).json() == []
    assert client.get(f"/api/reports/{a['id']}", headers=BOB).status_code == 404
    bob = gen(client, "monthly", "2024-05-01", headers=BOB)          # Bob gets his own (empty) report
    assert bob["id"] != a["id"] and bob["data"]["totals"]["spend"] == "0.00"
