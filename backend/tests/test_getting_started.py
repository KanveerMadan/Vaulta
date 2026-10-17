"""Guided tour state and the getting-started checklist (Phase 8 steps 1–2)."""

from tests.conftest import as_user
from tests.test_import_batch import post, row
from tests.test_manual_entry import manual
from tests.test_demo import demo_headers  # noqa: F401  (fixture)

ALICE, BOB = as_user("alice"), as_user("bob")


def items(client, headers=ALICE):
    return {i["id"]: i["done"] for i in client.get("/api/checklist", headers=headers).json()["items"]}


def test_tour_state_is_server_side_and_replayable(client):
    assert client.get("/api/tour", headers=ALICE).json() == {"available": True, "status": "new", "step": 0}
    client.patch("/api/tour", json={"status": "active"}, headers=ALICE)
    client.patch("/api/tour", json={"step": 3}, headers=ALICE)
    assert client.get("/api/tour", headers=ALICE).json()["step"] == 3            # resumes on any device
    done = client.patch("/api/tour", json={"status": "skipped"}, headers=ALICE).json()
    assert done["status"] == "skipped" and done["step"] == 3
    replay = client.patch("/api/tour", json={"status": "active"}, headers=ALICE).json()
    assert (replay["status"], replay["step"]) == ("active", 0)
    assert client.patch("/api/tour", json={}, headers=ALICE).status_code == 422
    assert client.patch("/api/tour", json={"status": "new"}, headers=ALICE).status_code == 422
    assert client.get("/api/tour", headers=BOB).json()["status"] == "new"        # per user


def test_checklist_ticks_from_what_the_user_did(client):
    client.get("/auth/me", headers=ALICE)
    assert not items(client)["first_import"]
    post(client, [row()])                                                         # a statement import
    client.post("/api/transactions", json=manual(merchant="Auto", category="Transport"), headers=ALICE)   # cash
    client.post("/api/budgets", json={"category": "Groceries", "monthly_limit": "5000"}, headers=ALICE)
    t = client.get("/api/transactions", headers=ALICE).json()["items"][0]
    client.patch(f"/api/transactions/{t['id']}", json={"category": "Travel"}, headers=ALICE)
    client.get("/api/review", headers=ALICE)
    done = items(client)
    for key in ("first_import", "cash_expense", "budget", "recategorise", "review"):
        assert done[key], key
    for key in ("first_alert", "telegram", "ask_ai", "report"):
        assert not done[key], key
    body = client.get("/api/checklist", headers=ALICE).json()
    assert body["done"] == sum(done.values()) and body["total"] == 10
    assert not any(items(client, BOB)[k] for k in ("first_import", "budget", "review"))   # Bob did none of it


def test_checklist_can_be_dismissed_and_restored(client):
    assert client.patch("/api/checklist", json={"dismissed": True}, headers=ALICE).json()["dismissed"] is True
    assert client.get("/api/checklist", headers=ALICE).json()["dismissed"] is True
    assert client.patch("/api/checklist", json={"dismissed": False}, headers=ALICE).json()["dismissed"] is False


def test_neither_exists_in_the_demo(client, demo_headers):
    assert client.get("/api/tour", headers=demo_headers).json()["available"] is False
    assert client.get("/api/checklist", headers=demo_headers).json()["available"] is False
    assert client.patch("/api/tour", json={"status": "active"}, headers=demo_headers).status_code == 403


def test_tour_and_checklist_state_doesnt_restart_setup_for_existing_accounts(client):
    from tests.test_end_to_end import USER, load_three_months
    load_three_months(client)                              # an account with data from before onboarding existed
    client.get("/api/review", headers=USER)                # records review_opened_at in users.onboarding
    client.patch("/api/tour", json={"status": "skipped"}, headers=USER)
    assert client.get("/api/onboarding", headers=USER).json()["status"] == "skipped"
