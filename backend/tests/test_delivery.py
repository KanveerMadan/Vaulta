"""Report delivery: scheduler timing, idempotency, email, unsubscribe, settings."""

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core import clock
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.report import Report
from app.models.user import User
from app.services import email, scheduler
from app.services.report_email import unsubscribe_token
from tests.conftest import as_user, user_session
from tests.test_end_to_end import USER, frozen_today, load_three_months  # noqa: F401 (fixture)

SECRET = "s3cret-for-tests"
IST = ZoneInfo("Asia/Kolkata")


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "INTERNAL_SECRET", SECRET)
    monkeypatch.setattr(email, "configured", lambda: True)
    monkeypatch.setattr(email, "send", lambda to, subject, html, text, headers=None: sent.append(
        {"to": to, "subject": subject, "html": html, "text": text, "headers": headers}) or "id")
    monkeypatch.setattr(scheduler, "purge_old", lambda db, user_id=None: 0)
    return sent


def run_at(client, monkeypatch, when):
    monkeypatch.setattr(clock, "now", lambda: when)
    res = client.post("/internal/run-reports", headers={"X-Internal-Secret": SECRET})
    assert res.status_code == 200, res.text
    return res.json()


def user(field=None, value=None, uid="rahul"):
    with user_session(uid) as (db, u):
        if field:
            setattr(u, field, value)
            db.commit()
        return u.id


def test_internal_endpoint_needs_the_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_SECRET", "")
    assert client.post("/internal/run-reports", headers={"X-Internal-Secret": ""}).status_code == 503
    monkeypatch.setattr(settings, "INTERNAL_SECRET", SECRET)
    assert client.post("/internal/run-reports").status_code == 401
    assert client.post("/internal/run-reports", headers={"X-Internal-Secret": "wrong"}).status_code == 401
    assert client.post("/internal/run-reports", headers=USER).status_code == 401        # a user's login isn't enough
    assert client.post("/internal/run-reports", headers={"X-Internal-Secret": SECRET}).status_code == 200


@pytest.mark.parametrize("period_type, when, expected", [
    ("weekly", utc(2024, 6, 30, 13, 30), "2024-06-30"),   # Sunday 19:00 IST → the week ending today
    ("weekly", utc(2024, 6, 30, 13, 29), "2024-06-23"),   # 18:59 → still last week's
    ("weekly", utc(2024, 7, 3, 6, 0), "2024-06-30"),      # Wednesday → the week that ended Sunday
    ("monthly", utc(2024, 7, 1, 3, 30), "2024-06-30"),    # 1st 09:00 IST → June
    ("monthly", utc(2024, 7, 1, 3, 29), "2024-05-31"),
    ("annual", utc(2025, 1, 1, 3, 30), "2024-12-31"),     # 1 Jan 09:00 IST → last year
    ("annual", utc(2025, 1, 1, 3, 29), "2023-12-31"),
])
def test_due_day(period_type, when, expected):
    assert scheduler.due_day(period_type, when.astimezone(IST)).isoformat() == expected


def test_monthly_run_builds_emails_once(client, monkeypatch, outbox):
    load_three_months(client)
    first = run_at(client, monkeypatch, utc(2024, 7, 1, 3, 30))
    # June built; the week 24–30 June and the year 2023 had no transactions
    assert {k: first[k] for k in ("generated", "emailed", "skipped_empty", "errors")} == {
        "generated": 1, "emailed": 1, "skipped_empty": 2, "errors": 0}
    [mail] = outbox
    with user_session("rahul") as (db, _):
        report = db.query(Report).one()
        assert (report.period_type, report.period_start.isoformat(), report.emailed_at is not None) == ("monthly", "2024-06-01", True)
    assert mail["to"] == "rahul@test.local"
    assert mail["subject"] == "Your monthly Vaulta report: June 2024"
    assert f"{settings.APP_BASE_URL}/reports/{report.id}" in mail["html"]
    assert f"Full report: {settings.APP_BASE_URL}/reports/{report.id}" in mail["text"]
    assert "₹25,599" in mail["html"] and "₹25,599" in mail["text"]
    assert mail["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "/unsubscribe?token=" in mail["headers"]["List-Unsubscribe"] and ":monthly:" in mail["headers"]["List-Unsubscribe"]
    for private in ("R***@okaxis", "UPI-RAVI KUMAR", "612400000408", "NEFT CR-ACME"):
        assert private not in mail["html"] and private not in mail["text"]

    again = run_at(client, monkeypatch, utc(2024, 7, 1, 4, 30))             # next hour
    assert (again["generated"], again["emailed"]) == (0, 0)
    assert len(outbox) == 1
    with user_session("rahul") as (db, _):
        assert db.query(Report).count() == 1


def test_failed_email_is_retried_next_hour(client, monkeypatch, outbox):
    load_three_months(client)

    def down(*a, **k):
        raise email.EmailError("Resend: ConnectError")
    monkeypatch.setattr(email, "send", down)
    first = run_at(client, monkeypatch, utc(2024, 7, 1, 3, 30))
    assert (first["generated"], first["emailed"], first["errors"]) == (1, 0, 1)
    monkeypatch.setattr(email, "send", lambda to, subject, html, text, headers=None: outbox.append(subject) or "id")
    second = run_at(client, monkeypatch, utc(2024, 7, 1, 4, 30))
    assert (second["generated"], second["emailed"], second["errors"]) == (0, 1, 0)
    assert outbox == ["Your monthly Vaulta report: June 2024"]


def test_preferences(client, monkeypatch, outbox):
    load_three_months(client)
    user("email_monthly", False)
    assert run_at(client, monkeypatch, utc(2024, 7, 1, 3, 30))["generated"] == 1
    assert outbox == []                                         # built, not emailed
    with user_session("rahul") as (db, _):
        db.query(Report).delete()
        db.commit()
    user("reports_monthly", False)
    assert run_at(client, monkeypatch, utc(2024, 7, 1, 3, 30))["generated"] == 0


def test_users_timezone_decides_what_is_due(client, monkeypatch, outbox):
    load_three_months(client)
    user("timezone", "America/New_York")
    run_at(client, monkeypatch, utc(2024, 7, 1, 3, 30))             # 30 June 23:30 in New York
    with user_session("rahul") as (db, _):
        assert [(r.period_type, r.period_start.isoformat()) for r in db.query(Report)] == [("monthly", "2024-05-01")]


def test_unsubscribe(client, monkeypatch, outbox):
    load_three_months(client)
    with user_session("rahul") as (db, u):
        monthly, weekly = unsubscribe_token(u, "monthly"), unsubscribe_token(u, "weekly")
    page = client.get(f"/unsubscribe?token={monthly}")
    assert page.status_code == 200 and "won't get monthly report emails" in page.text
    s = client.get("/api/settings", headers=USER).json()
    assert (s["email_monthly"], s["email_weekly"], s["reports_monthly"]) == (False, True, True)
    assert client.post(f"/unsubscribe?token={weekly}").status_code == 200        # one-click
    assert client.get("/api/settings", headers=USER).json()["email_weekly"] is False
    tampered = monthly[:-1] + ("1" if monthly[-1] == "0" else "0")              # always a different last character
    assert client.get(f"/unsubscribe?token={tampered}").status_code == 400
    assert client.get("/unsubscribe?token=nonsense").status_code == 400
    forged = monthly.replace(":monthly:", ":annual:")
    assert client.get(f"/unsubscribe?token={forged}").status_code == 400
    assert client.get("/api/settings", headers=USER).json()["email_annual"] is True


def test_settings(client):
    s = client.get("/api/settings", headers=USER).json()
    channels = s.pop("alert_channels")
    assert channels["duplicate_charge"] == {"telegram": True, "email": True} and channels["price_change"] == {"telegram": True, "email": False}
    assert (s.pop("quiet_start"), s.pop("quiet_end")) == (22, 8)
    assert s == {"ai_chat_enabled": True, "timezone": "Asia/Kolkata", "reports_weekly": True, "reports_monthly": True,
                 "reports_annual": True, "email_weekly": True, "email_monthly": True, "email_annual": True,
                 "email_configured": email.configured()}
    assert client.patch("/api/settings", json={"timezone": "Mars/Olympus"}, headers=USER).status_code == 422
    assert client.patch("/api/settings", json={"timezone": "Europe/London", "email_weekly": False}, headers=USER).json()[
        "timezone"] == "Europe/London"
    assert client.patch("/api/settings", json={"x": 1}, headers=USER).status_code == 422
    assert client.get("/api/settings", headers=as_user("bob")).json()["timezone"] == "Asia/Kolkata"


def test_run_purges_old_chat_history(client, monkeypatch):
    from app.models.chat import ChatMessage
    monkeypatch.setattr(settings, "INTERNAL_SECRET", SECRET)
    client.get("/api/settings", headers=USER)          # first request creates the user
    uid = user()
    with user_session("rahul") as (db, _):
        db.add(ChatMessage(user_id=uid, session_id=uuid.uuid4(), role="user", content="old",
                           created_at=datetime.now(timezone.utc) - timedelta(days=31)))
        db.commit()
    assert run_at(client, monkeypatch, utc(2024, 7, 1, 3, 30))["chat_messages_purged"] == 1
