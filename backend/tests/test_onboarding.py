"""First-login onboarding: state, resume, coverage meter, test email."""

from datetime import timedelta

from app.core import clock
from app.core.database import SessionLocal
from app.models.inbound import InboundEvent
from app.models.user import User
from tests.conftest import as_user
from tests.test_end_to_end import USER, load_three_months

ALICE, BOB = as_user("alice"), as_user("bob")


def ob(client, headers=ALICE):
    return client.get("/api/onboarding", headers=headers).json()


def patch(client, body, headers=ALICE):
    res = client.patch("/api/onboarding", json=body, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_new_user_starts_at_basics_and_can_resume(client):
    s = ob(client)
    assert (s["step"], s["status"], s["coverage"]["percent"]) == ("basics", "new", 0)
    assert {"key": "hdfc", "name": "HDFC Bank"} in s["bank_choices"] and "phonepe" not in {b["key"] for b in s["bank_choices"]}
    assert "PhonePe" in s["upi_choices"]
    s = patch(client, {"income": "85000", "payday": 1, "banks": ["hdfc", "sbicard"], "upi_apps": ["Google Pay"],
                       "timezone": "Asia/Dubai", "step": "connect", "status": "active"})
    assert (s["income"], s["payday"], s["banks"], s["timezone"], s["step"]) == ("85000", 1, ["hdfc", "sbicard"], "Asia/Dubai", "connect")
    assert s["coverage"]["parts"]["basics"] == 10 and s["coverage"]["percent"] == 10
    assert client.get("/api/settings", headers=ALICE).json()["timezone"] == "Asia/Dubai"
    assert ob(client)["step"] == "connect"                    # resumes where it was left
    s = patch(client, {"status": "skipped"})
    assert s["status"] == "skipped" and s["skipped_at"]
    s = patch(client, {"status": "active", "step": "import"})   # Settings → Resume setup
    assert (s["status"], s["step"], s["banks"]) == ("active", "import", ["hdfc", "sbicard"])
    assert ob(client, BOB)["step"] == "basics"


def test_validation(client):
    for bad in ({"banks": ["nope"]}, {"upi_apps": ["Venmo"]}, {"payday": 32}, {"step": "x"}, {"income": "-1"},
                {"timezone": "Mars/Base"}, {"status": "finished"}, {"extra": True}):
        assert client.patch("/api/onboarding", json=bad, headers=ALICE).status_code == 422, bad


def test_coverage_meter_counts_history_review_and_sources(client):
    load_three_months(client)
    s = ob(client, USER)
    parts = s["coverage"]["parts"]
    assert parts["statements"] == 30 and parts["email"] == 0 and parts["telegram"] == 0
    open_cards = client.get("/api/review", headers=USER).json()["count"]
    assert parts["review"] == max(25 - 5 * open_cards, 0)
    with SessionLocal() as db:
        user = db.query(User).filter_by(firebase_uid="rahul").one()
        user.telegram_chat_id = 42
        db.commit()
    assert ob(client, USER)["coverage"]["parts"]["telegram"] == 10


def test_send_test_email_is_verified_by_any_arrival(client):
    s = client.post("/api/onboarding/test-email", headers=ALICE).json()
    assert s["test_started_at"] and s["test_received"] is False
    with SessionLocal() as db:
        user = db.query(User).filter_by(firebase_uid="alice").one()
        db.add(InboundEvent(user_id=user.id, outcome="untrusted_sender", received_at=clock.now() - timedelta(hours=1)))
        db.commit()
    assert ob(client)["test_received"] is False                # arrived before the test started
    with SessionLocal() as db:
        user = db.query(User).filter_by(firebase_uid="alice").one()
        db.add(InboundEvent(user_id=user.id, outcome="untrusted_sender"))
        db.commit()
    s = ob(client)
    assert s["test_received"] is True and s["coverage"]["parts"]["email"] == 25
    assert ob(client, BOB)["test_received"] is False


def test_existing_accounts_are_not_forced_through_setup(client):
    load_three_months(client)
    assert ob(client, USER)["status"] == "skipped"
    assert patch(client, {"status": "active"}, headers=USER)["status"] == "active"
