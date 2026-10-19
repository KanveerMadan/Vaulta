"""Home screen (GET /api/home): every card from services/analytics.py."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core import clock
from app.core.database import SessionLocal
from app.models.inbound import InboundEvent
from app.models.user import User
from app.services import analytics
from tests.conftest import as_user, user_session
from tests.test_end_to_end import TODAY, USER, load_three_months

NEW = as_user("newcomer")


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)
    monkeypatch.setattr(clock, "now", lambda: datetime(2024, 6, 28, 12, tzinfo=timezone.utc))


def home(client, query="", headers=USER):
    res = client.get(f"/api/home{query}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_cards_for_the_current_month(client):
    load_three_months(client)
    client.post("/api/budgets", json={"category": None, "monthly_limit": "25000"}, headers=USER)
    client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "200"}, headers=USER)
    h = home(client)
    assert (h["month"], h["is_current_month"]) == ("2024-06", True)
    with user_session("rahul") as (db, _user):
        uid = _user.id
        assert h["safe_to_spend"]["amount"] == str(analytics.safe_to_spend_today(db, uid)["amount"])
        f = analytics.forecast_month_end(db, uid, TODAY)
    o = h["outlook"]
    assert o["forecast"] == str(f["forecast"]) and o["limit"] == "25000.00"
    assert o["difference"] == str(f["forecast"] - 25000)
    assert o["status"] == ("red" if f["forecast"] > 25000 else "amber" if f["forecast"] > 22500 else "green")
    assert h["budgets"]["overall"]["limit"] == "25000.00"
    [food] = h["budgets"]["categories"]
    assert (food["category"], food["spent"], food["over"]) == ("Food & Dining", "300.00", True)   # Swiggy in June
    assert h["attention"]["review_count"] >= len(h["attention"]["review_cards"]) > 0
    assert len(h["attention"]["review_cards"]) <= 2
    cov = h["coverage"]
    assert cov["statements"] == {"active": True, "from": "2024-04-01", "to": "2024-06-22", "months": 3}
    assert cov["needs_attention"] == ["email"] and cov["telegram"] == {"active": False}


def test_past_month_is_history(client):
    load_three_months(client)
    client.post("/api/budgets", json={"category": None, "monthly_limit": "25000"}, headers=USER)
    h = home(client, "?month=2024-05")
    assert h["is_current_month"] is False and h["safe_to_spend"] is None and h["upcoming"] == []
    assert (h["outlook"]["forecast"], h["outlook"]["difference"], h["outlook"]["status"]) == ("24099.00", "-901.00", "amber")
    assert h["budgets"]["total_spend"] == "24099.00"
    assert client.get("/api/home?month=2024-13", headers=USER).status_code == 422
    assert client.get("/api/home?month=june", headers=USER).status_code == 422


def test_empty_account(client):
    h = home(client, headers=NEW)
    assert h["safe_to_spend"]["amount"] is None
    assert h["outlook"]["status"] is None and h["outlook"]["forecast"] == "0.00"
    assert h["budgets"]["categories"] == [] and h["upcoming"] == []
    assert h["attention"] == {"review_count": 0, "review_cards": [], "anomaly_count": 0}
    assert h["coverage"]["needs_attention"] == ["statements", "email"]


def test_quiet_alerts_are_flagged_stale(client):
    home(client, headers=NEW)
    with user_session("newcomer") as (db, user):
        db.add(InboundEvent(user_id=user.id, outcome="parsed", bank_name="HDFC Bank",
                            received_at=clock.now() - timedelta(days=8)))
        db.commit()
    email = home(client, headers=NEW)["coverage"]["email"]
    assert (email["connected"], email["stale"], email["active"]) == (True, True, False)
    with user_session("newcomer") as (db, user):
        db.add(InboundEvent(user_id=user.id, outcome="parsed", bank_name="HDFC Bank", received_at=clock.now() - timedelta(minutes=2)))
        db.commit()
    cov = home(client, headers=NEW)["coverage"]
    assert cov["email"]["active"] is True and "email" not in cov["needs_attention"]


def test_home_is_per_user(client):
    load_three_months(client)
    h = home(client, headers=NEW)
    assert h["budgets"]["total_spend"] == "0.00" and h["coverage"]["statements"]["active"] is False
    assert h["attention"]["review_count"] == 0
