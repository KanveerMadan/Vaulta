"""services/analytics.py on the Phase 2 end-to-end fixture (today = 2024-06-28)."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.core.database import SessionLocal
from app.models.user import User
from app.services import analytics as a
from tests.test_end_to_end import TODAY, USER, frozen_today, load_three_months  # noqa: F401 (fixture)

APR = (date(2024, 4, 1), date(2024, 4, 30))
MAY = (date(2024, 5, 1), date(2024, 5, 31))
JUN = (date(2024, 6, 1), date(2024, 6, 30))
Q2 = (date(2024, 4, 1), date(2024, 6, 30))


@pytest.fixture
def ctx(client):
    load_three_months(client)
    with SessionLocal() as db:
        yield db, db.query(User).filter_by(firebase_uid="rahul").one().id


def groups(result):
    return [(g["label"], g["total"], g["count"]) for g in result["groups"]]


def test_spend_summary_groupings(ctx):
    db, uid = ctx
    apr = a.spend_summary(db, uid, *APR, "category")
    assert (apr["total"], apr["count"]) == (D("23199.00"), 5)
    assert groups(apr) == [("Rent & Housing", D("20000.00"), 1), ("Utilities", D("1200.00"), 1), ("Groceries", D("900.00"), 1),
                           ("Food & Dining", D("600.00"), 1), ("Entertainment", D("499.00"), 1)]
    assert groups(a.spend_summary(db, uid, *JUN, "merchant")) == [
        ("Rent", D("20000.00"), 1), ("Amazon", D("3000.00"), 2), ("Electricity Bill", D("1250.00"), 1),
        ("Netflix", D("649.00"), 1), ("Zepto", D("400.00"), 1), ("Swiggy", D("300.00"), 1)]
    assert groups(a.spend_summary(db, uid, *Q2, "person")) == [("Ravi Kumar", D("60000.00"), 3)]
    assert groups(a.spend_summary(db, uid, *Q2, "month")) == [
        ("2024-04-01", D("23199.00"), 5), ("2024-05-01", D("24099.00"), 5), ("2024-06-01", D("25599.00"), 7)]
    may_food = a.spend_summary(db, uid, date(2024, 5, 15), date(2024, 5, 18), "day")
    assert groups(may_food) == [("2024-05-15", D("1200.00"), 1), ("2024-05-18", D("-400.00"), 0)]   # refund nets
    week = a.spend_summary(db, uid, date(2024, 6, 17), date(2024, 6, 23), "week")
    assert groups(week) == [("2024-06-17", D("3000.00"), 2)]


def test_top_merchants_and_compare(ctx):
    db, uid = ctx
    assert [(m["label"], m["total"]) for m in a.top_merchants(db, uid, *MAY, 3)] == [
        ("Rent", D("20000.00")), ("Zepto", D("1500.00")), ("Electricity Bill", D("1300.00"))]
    c = a.compare_periods(db, uid, *JUN, *MAY, "category")
    assert (c["a"]["total"], c["b"]["total"], c["delta"], c["delta_pct"]) == (D("25599.00"), D("24099.00"), D("1500.00"), D("6.2"))
    assert [(r["label"], r["delta"], r["delta_pct"]) for r in c["rows"]] == [
        ("Shopping", D("2000.00"), None), ("Groceries", D("-1100.00"), D("-73.3")), ("Health", D("1000.00"), None),
        ("Food & Dining", D("-500.00"), D("-62.5")), ("Entertainment", D("150.00"), D("30.1")),
        ("Utilities", D("-50.00"), D("-3.8")), ("Rent & Housing", D("0.00"), D("0.0"))]


def test_income_and_savings(ctx):
    db, uid = ctx
    inc = a.income_summary(db, uid, *JUN)
    assert inc["total"] == D("81500.00")
    assert [(s["label"], s["total"]) for s in inc["sources"]] == [
        ("Neft Cr Acme Corp Payroll", D("80000.00")), ("Received from People", D("1500.00"))]
    sr = a.savings_rate(db, uid, *JUN)
    assert (sr["income"], sr["spend"], sr["saved"], sr["rate_pct"]) == (D("81500.00"), D("25599.00"), D("55901.00"), D("68.6"))
    assert a.savings_rate(db, uid, date(2024, 1, 1), date(2024, 1, 31))["rate_pct"] is None


def test_budget_status(ctx, client):
    client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "1000"}, headers=USER)
    client.post("/api/budgets", json={"category": None, "monthly_limit": "25000"}, headers=USER)
    db, uid = ctx
    b = a.budget_status(db, uid, date(2024, 6, 1))
    assert (b["month"], b["days_left"], b["total_spend"]) == ("2024-06", 2, D("25599.00"))
    assert b["overall"] == {"category": "Overall", "limit": D("25000.00"), "spent": D("25599.00"), "remaining": D("-599.00"),
                            "pct": D("102.4"), "over": True}
    assert b["categories"] == [{"category": "Food & Dining", "limit": D("1000.00"), "spent": D("300.00"),
                                "remaining": D("700.00"), "pct": D("30.0"), "over": False}]
    assert a.safe_to_spend_today(db, uid)["amount"] == D("0.00")        # already over the overall cap


def test_recurring_upcoming_people(ctx):
    db, uid = ctx
    r = a.recurring_overview(db, uid)
    assert r["monthly_committed"] == D("21899.00")
    assert sorted(s["name"] for s in r["series"]) == ["Electricity Bill", "Netflix", "Ravi Kumar"]
    assert [(s["name"], s["next_expected"]) for s in a.upcoming(db, uid, 14)] == [
        ("Ravi Kumar", "2024-07-03"), ("Electricity Bill", "2024-07-07"), ("Netflix", "2024-07-10")]
    assert a.upcoming(db, uid, 5) == [a.upcoming(db, uid, 14)[0]]
    people = {p["name"]: p for p in a.person_balances(db, uid)}
    assert (people["Ankit Jain"]["balance"], people["Ankit Jain"]["outstanding_days"]) == (D("1000.00"), 77)


def test_forecast_and_safe_to_spend(ctx):
    db, uid = ctx
    jun = a.forecast_month_end(db, uid, date(2024, 6, 1))
    # 25599 so far; 21899 of it recurring → 3700 discretionary over 28 days = 132.14/day × 2 days left
    assert (jun["so_far"], jun["recurring_due"], jun["discretionary_daily"], jun["days_left"], jun["forecast"]) == (
        D("25599.00"), D("0.00"), D("132.14"), 2, D("25863.28"))
    jul = a.forecast_month_end(db, uid, date(2024, 7, 1))
    assert (jul["so_far"], jul["recurring_due"], jul["forecast"]) == (D("0.00"), D("21899.00"), D("21899.00"))
    assert [i["name"] for i in jul["recurring_due_items"]] == ["Ravi Kumar", "Electricity Bill", "Netflix"]
    assert a.forecast_month_end(db, uid, date(2024, 5, 1))["forecast"] == D("24099.00")
    safe = a.safe_to_spend_today(db, uid)
    # no budget → this month's income: (81500 − 25599 − 0) ÷ 3 days (28, 29, 30)
    assert (safe["basis"], safe["remaining"], safe["days_left_including_today"], safe["amount"]) == (
        "income this month", D("55901.00"), 3, D("18633.67"))
