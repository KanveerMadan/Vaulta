"""Simulations (Phase 8 step 4): sample input through the real pipelines, as sample rows; nothing written in the demo."""

import pytest

from app.models.inbound import InboundEvent
from tests.conftest import as_user, user_session
from tests.test_demo import demo_headers  # noqa: F401  (fixture)

ALICE, BOB = as_user("alice"), as_user("bob")


@pytest.mark.parametrize("bank, merchant, category", [
    ("hdfc", "Swiggy", "Food & Dining"), ("icici", "Uber", "Transport"), ("sbi", "Zomato", "Food & Dining"),
    ("axis", "BigBasket", "Groceries"),
])
def test_a_sample_alert_becomes_a_sample_transaction(client, bank, merchant, category):
    client.get("/auth/me", headers=ALICE)
    res = client.post("/api/simulations/bank-alert", json={"bank": bank}, headers=ALICE)
    assert res.status_code == 200, res.text
    body = res.json()
    t = body["transaction"]
    assert body["saved"] and t["is_sample"] and (t["merchant_clean"], t["category"]) == (merchant, category)
    assert body["email"]["from"].endswith(">") and body["email"]["text"]          # the sample email it read, shown to the user
    listed = client.get("/api/transactions", headers=ALICE).json()["items"]
    assert [x["id"] for x in listed if x["is_sample"]] == [t["id"]]
    # it went through the alert pipeline but isn't a forwarded alert: no inbound event, no checklist tick, no totals
    with user_session("alice") as (db, user):
        assert db.query(InboundEvent).filter(InboundEvent.user_id == user.id).count() == 0
    items = {i["id"]: i["done"] for i in client.get("/api/checklist", headers=ALICE).json()["items"]}
    assert not items["first_alert"]
    assert client.get("/api/transactions/summary", headers=ALICE).json()["total_spend"] in ("0", "0.00", 0)


def test_quick_add_shows_the_telegram_reply_and_saves_a_sample(client):
    client.get("/auth/me", headers=ALICE)
    preview = client.post("/api/simulations/quick-add", json={"text": "150 auto cash"}, headers=ALICE).json()
    assert preview["saved"] is False and preview["reply"]["text"].startswith("₹150 · Auto · Transport · today · cash")
    assert preview["reply"]["buttons"][0] == "✓ Save"
    assert client.get("/api/simulations", headers=ALICE).json() == {"samples": 0}       # a preview writes nothing
    saved = client.post("/api/simulations/quick-add", json={"text": "150 auto cash", "save": True}, headers=ALICE).json()
    assert saved["saved"] and saved["transaction"]["is_sample"] and saved["transaction"]["category"] == "Transport"
    assert client.get("/api/simulations", headers=ALICE).json() == {"samples": 1}
    assert client.get("/api/simulations", headers=BOB).json() == {"samples": 0}
    assert not {i["id"]: i["done"] for i in client.get("/api/checklist", headers=ALICE).json()["items"]}["cash_expense"]
    assert client.post("/api/simulations/quick-add", json={"text": "auto"}, headers=ALICE).status_code == 422
    assert client.post("/api/simulations/bank-alert", json={"bank": "nope"}, headers=ALICE).status_code == 422


def test_the_demo_can_simulate_but_nothing_is_written(client, demo_headers):
    before = len(client.get("/api/transactions?page_size=200", headers=demo_headers).json()["items"])
    alert = client.post("/api/simulations/bank-alert", json={"bank": "hdfc"}, headers=demo_headers)
    assert alert.status_code == 200 and alert.json()["saved"] is False
    assert alert.json()["transaction"]["merchant_clean"] == "Swiggy"
    add = client.post("/api/simulations/quick-add", json={"text": "150 auto cash", "save": True}, headers=demo_headers).json()
    assert add["saved"] is False and add["reply"]["text"].startswith("₹150")
    assert len(client.get("/api/transactions?page_size=200", headers=demo_headers).json()["items"]) == before
    assert client.delete("/api/simulations", headers=demo_headers).status_code == 403            # still read-only otherwise


def test_simulations_are_rate_limited(client, monkeypatch):
    from app.api.routes import simulations as routes
    monkeypatch.setattr(routes, "SIMULATIONS_PER_HOUR", 2)
    client.get("/auth/me", headers=ALICE)
    codes = [client.post("/api/simulations/quick-add", json={"text": "10 tea"}, headers=ALICE).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
