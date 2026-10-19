"""Proactive alerts (services/alerts.py): triggers, dedup, channels, quiet hours, privacy."""

import json
from datetime import datetime, timezone

import pytest

from app.core import clock
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.alert import Alert
from app.models.user import User
from app.services import email, telegram
from tests.conftest import as_user, user_session
from tests.test_anomalies import gpay, r
from tests.test_end_to_end import TODAY, USER

BOB = as_user("bob")
NOON_UTC = datetime(2024, 6, 28, 6, 30, tzinfo=timezone.utc)        # 12:00 IST
NIGHT_UTC = datetime(2024, 6, 28, 17, 30, tzinfo=timezone.utc)      # 23:00 IST


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)       # 2024-06-28
    monkeypatch.setattr(clock, "now", lambda: NOON_UTC)


@pytest.fixture
def outbox(monkeypatch):
    sent = {"telegram": [], "email": []}
    monkeypatch.setattr(telegram, "configured", lambda: True)
    monkeypatch.setattr(telegram, "call", lambda method, payload: sent["telegram"].append(payload["text"]) or {"ok": True})
    monkeypatch.setattr(email, "configured", lambda: True)
    monkeypatch.setattr(email, "send", lambda to, subject, html, text, headers=None: sent["email"].append((to, subject, text)) or "id")
    return sent


def load(client, *rows, headers=USER):
    assert client.post("/api/import/batch", json={"rows": list(rows)}, headers=headers).status_code == 200


def alerts(client, headers=USER):
    return client.get("/api/alerts", headers=headers).json()


def messages(client, headers=USER):
    return sorted(a["message"] for a in alerts(client, headers)["items"])


def link_telegram(uid="rahul", chat=555):
    with user_session(uid) as (db, _user):
        _user.telegram_chat_id = chat
        db.commit()


def test_budget_80_and_100_once_each(client):
    client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "1000"}, headers=USER)
    client.post("/api/budgets", json={"category": "Transport", "monthly_limit": "100"}, headers=USER)
    load(client, r("2024-06-20", "SWIGGY", "800.00"))
    assert messages(client) == ["Food & Dining budget 80% used: ₹800 of ₹1,000 in June."]
    load(client, r("2024-06-21", "SWIGGY", "50.00"))
    assert len(messages(client)) == 1                                   # still 85%: nothing new
    load(client, r("2024-06-22", "SWIGGY", "200.00"), r("2024-06-22", "UBER INDIA", "150.00"))
    assert messages(client) == [
        "Food & Dining budget 80% used: ₹800 of ₹1,000 in June.",
        "Food & Dining budget used up: ₹1,050 of ₹1,000 in June.",
        "Transport budget used up: ₹150 of ₹100 in June.",              # straight past 100%: one alert
    ]
    client.post("/api/transactions/reanalyze", headers=USER)
    assert len(messages(client)) == 3


def test_anomaly_alerts_and_default_email(client, outbox):
    load(client, gpay("2024-06-27T12:00:00", "SWIGGY", "450.00", "612400000101"),
         gpay("2024-06-27T12:03:00", "SWIGGY", "450.00", "612400000102"),
         r("2024-06-24", "UPI-ZOMATO-zomato@hdfcbank-FAILED", "350.00", ref="412300000009"))
    assert messages(client) == [
        "A failed payment of ₹350 to Zomato on 24 Jun hasn't been refunded yet.",
        "Possible duplicate charge: Swiggy ₹450, twice within 10 minutes.",
    ]
    assert [s for _, s, _ in outbox["email"]] == ["Vaulta: Failed payment not refunded", "Vaulta: Possible duplicate charge"] or \
        sorted(s for _, s, _ in outbox["email"]) == ["Vaulta: Failed payment not refunded", "Vaulta: Possible duplicate charge"]
    assert {to for to, _, _ in outbox["email"]} == {"rahul@test.local"}
    assert outbox["telegram"] == []                                     # not linked


def test_unusual_amount_price_change_and_salary(client, outbox):
    usual = [r(f"2024-05-{d:02d}", "SWIGGY", amt) for d, amt in zip((1, 3, 5, 7, 9), ("300.00", "280.00", "320.00", "300.00", "310.00"))]
    netflix = [r(f"2024-{m:02d}-24", "NETFLIX COM", "499.00") for m in (3, 4, 5)]
    load(client, *usual, *netflix, r("2024-04-01", "NEFT CR-ACME CORP PAYROLL", "80000.00", "credit"))
    assert messages(client) == []                                       # all older than 7 days
    load(client, r("2024-06-25", "SWIGGY", "950.00"), r("2024-06-24", "NETFLIX COM", "649.00"),
         r("2024-06-26", "NEFT CR-ACME CORP PAYROLL", "80000.00", "credit"),
         r("2024-05-27", "UPI-RENT SHARE-XXXX", "500.00", "credit"), r("2024-06-26", "UPI-RENT SHARE-XXXX", "500.00", "credit"),
         r("2024-06-27", "UPI-ONE OFF-XXXX", "700.00", "credit"))
    got = messages(client)
    assert "Unusual amount: ₹950 at Swiggy (usually about ₹300)." in got
    assert "Netflix changed price: ₹499 → ₹649." in got
    # ₹80,000 (≥ ₹10,000) and ₹500 from a source that also paid 30 days earlier; the ₹700 one-off isn't
    assert sorted(m for m in got if m.startswith("Income")) == ["Income received: ₹500 from Rent.", "Income received: ₹80,000."]
    assert all("XXXX" not in m and "NEFT" not in m and "UPI-" not in m for m in got)      # labels, never narrations
    assert outbox["email"] == []                                        # these types aren't emailed by default


def test_telegram_quiet_hours_and_channel_settings(client, outbox, monkeypatch):
    client.get("/api/settings", headers=USER)
    link_telegram()
    client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "1000"}, headers=USER)
    monkeypatch.setattr(clock, "now", lambda: NIGHT_UTC)
    load(client, r("2024-06-27", "SWIGGY", "850.00"))
    assert outbox["telegram"] == []                                     # 23:00 IST: held
    with user_session("rahul") as (db, _):
        assert [a.telegram_status for a in db.query(Alert)] == ["queued"]
    monkeypatch.setattr(settings, "INTERNAL_SECRET", "x" * 40)
    run = lambda: client.post("/internal/run-reports", headers={"X-Internal-Secret": "x" * 40}).json()
    run()
    assert outbox["telegram"] == []                                     # still night
    monkeypatch.setattr(clock, "now", lambda: datetime(2024, 6, 29, 3, 0, tzinfo=timezone.utc))   # 08:30 IST
    assert run()["alerts_sent"] == 1
    assert outbox["telegram"] == ["Food & Dining budget 80% used: ₹850 of ₹1,000 in June."]
    run()
    assert len(outbox["telegram"]) == 1

    s = client.patch("/api/settings", json={"alert_channels": {"budget_threshold": {"telegram": False, "email": True}},
                                            "quiet_start": 23, "quiet_end": 6}, headers=USER).json()
    assert s["alert_channels"]["budget_threshold"] == {"telegram": False, "email": True}
    assert s["alert_channels"]["duplicate_charge"] == {"telegram": True, "email": True}
    assert (s["quiet_start"], s["quiet_end"]) == (23, 6)
    load(client, r("2024-06-27", "SWIGGY", "200.00"))                   # → 100%
    assert len(outbox["telegram"]) == 1 and outbox["email"][-1][1] == "Vaulta: Budget reaches 80% / 100%"
    for bad in ({"alert_channels": {"nope": {"email": True}}}, {"alert_channels": {"price_change": {"sms": True}}},
                {"quiet_start": 24}, {"quiet_end": -1}):
        assert client.patch("/api/settings", json=bad, headers=USER).status_code == 422, bad


def test_renewal_tomorrow_from_the_hourly_run(client, outbox, monkeypatch):
    load(client, *[r(f"2024-{m:02d}-29", "NETFLIX COM", "649.00") for m in (3, 4, 5)])
    link_telegram()
    monkeypatch.setattr(settings, "INTERNAL_SECRET", "x" * 40)
    for _ in range(2):
        client.post("/internal/run-reports", headers={"X-Internal-Secret": "x" * 40})
    assert messages(client) == ["Netflix is due tomorrow: ₹649."]
    assert outbox["telegram"] == ["Netflix is due tomorrow: ₹649."]


def test_bell_unread_and_isolation(client):
    client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "100"}, headers=USER)
    client.post("/api/budgets", json={"category": "Transport", "monthly_limit": "100"}, headers=USER)
    load(client, r("2024-06-20", "SWIGGY", "800.00"), r("2024-06-20", "UBER INDIA", "800.00"))
    a = alerts(client)
    assert a["unread"] == 2 and all(not x["read"] for x in a["items"])
    assert alerts(client, BOB) == {"unread": 0, "items": []}
    client.post("/api/alerts/read", json={"ids": [x["id"] for x in a["items"]]}, headers=BOB)   # Bob can't mark Alice's
    assert alerts(client)["unread"] == 2
    after = client.post("/api/alerts/read", json={"ids": [a["items"][0]["id"]]}, headers=USER).json()
    assert after["unread"] == 1
    assert client.post("/api/alerts/read", json={}, headers=USER).json()["unread"] == 0
    assert client.post("/api/alerts/read", json={"ids": ["x"]}, headers=USER).status_code == 422
    with user_session("rahul") as (db, _):
        stored = json.dumps([a.message for a in db.query(Alert)])
    assert "SWIGGY" not in stored and "UBER INDIA" not in stored


def test_alert_email_escapes_the_message(monkeypatch):
    from app.services import alerts as alerts_service
    sent = []
    monkeypatch.setattr(email, "send", lambda to, subject, html, text, headers=None: sent.append(html) or "id")
    alert = Alert(type="duplicate_charge", message='Possible duplicate charge: <img src=x onerror=alert(1)> ₹450.')
    alerts_service._send_email(alert, User(email="a@b.test"), NOON_UTC)
    assert "<img" not in sent[0] and "&lt;img src=x" in sent[0]
