"""Two-level taxonomy, custom subcategories, tags and subcategory budgets (Phase 9 step 1)."""

import json
from pathlib import Path

from app.services import taxonomy
from app.services.merchant_normalizer import _PATTERNS, SUBCATEGORIES
from tests.conftest import as_user
from tests.test_import_batch import post, row
from tests.test_manual_entry import manual

ALICE, BOB = as_user("alice"), as_user("bob")
ROOT = Path(__file__).resolve().parents[2]


def test_the_frontend_has_the_same_taxonomy():
    backend = json.loads((ROOT / "backend/app/data/taxonomy.json").read_text())
    assert json.loads((ROOT / "frontend/src/lib/taxonomy.json").read_text()) == backend


def test_taxonomy_shape():
    ids = [s["id"] for g in taxonomy.TAXONOMY["groups"] for s in g["subcategories"]]
    assert len(ids) == len(set(ids)) and 100 <= len(ids) <= 150
    for g in taxonomy.TAXONOMY["groups"]:
        for s in g["subcategories"]:
            assert s["id"].split(".")[0] == g["id"] and s["definition"].strip()
    # every category that existed before the taxonomy is still a group, so no stored value became invalid
    before = {"Food & Dining", "Groceries", "Transport", "Shopping", "Utilities", "Rent & Housing", "Health",
              "Entertainment", "Travel", "Education", "Software & Cloud", "Finance", "Insurance", "Investments",
              "Taxes & Government", "Sent to People", "Received from People", "Transfers", "Cash", "Misc cash", "Other"}
    assert before <= taxonomy.GROUP_NAMES


def test_every_normalizer_merchant_has_a_subcategory_in_its_group():
    for _, merchant, category, _ in _PATTERNS:
        assert taxonomy.group_of(SUBCATEGORIES[merchant]) == category, merchant


def test_imports_get_a_subcategory_and_edits_move_the_pair(client):
    post(client, [row()])
    t = client.get("/api/transactions", headers=ALICE).json()["items"][0]
    assert (t["category"], t["subcategory"]) == ("Food & Dining", "food.delivery")

    # a subcategory sets its group
    r = client.patch(f"/api/transactions/{t['id']}", json={"subcategory": "groceries.quick_commerce"}, headers=ALICE)
    assert (r.json()["category"], r.json()["subcategory"]) == ("Groceries", "groceries.quick_commerce")
    # a group that doesn't contain it is refused
    assert client.patch(f"/api/transactions/{t['id']}", json={"category": "Travel", "subcategory": "food.cafe"},
                        headers=ALICE).status_code == 422
    assert client.patch(f"/api/transactions/{t['id']}", json={"subcategory": "food.nonsense"}, headers=ALICE).status_code == 422
    # a new group alone drops the subcategory; re-running detection keeps the user's pair
    r = client.patch(f"/api/transactions/{t['id']}", json={"category": "Shopping"}, headers=ALICE)
    assert (r.json()["category"], r.json()["subcategory"]) == ("Shopping", None)
    client.post("/api/transactions/reanalyze", headers=ALICE)
    t = client.get("/api/transactions", headers=ALICE).json()["items"][0]
    assert (t["category"], t["subcategory"]) == ("Shopping", None)


def test_two_consistent_subcategory_edits_make_a_rule(client):
    post(client, [row(date="2024-03-05", reference="412345678901"), row(date="2024-03-09", reference="412345678902"),
                  row(date="2024-03-12", reference="412345678903")])
    ids = [t["id"] for t in client.get("/api/transactions", headers=ALICE).json()["items"]]
    client.patch(f"/api/transactions/{ids[0]}", json={"subcategory": "food.canteen"}, headers=ALICE)
    r = client.patch(f"/api/transactions/{ids[1]}", json={"subcategory": "food.canteen"}, headers=ALICE).json()
    assert r["rule_applied"]["value"] == "food.canteen" and r["rule_applied"]["applied_count"] == 1
    third = next(t for t in client.get("/api/transactions", headers=ALICE).json()["items"] if t["id"] == ids[2])
    assert (third["category"], third["subcategory"]) == ("Food & Dining", "food.canteen")


def test_custom_subcategories(client):
    created = client.post("/api/categories/subcategories", json={"group": "Food & Dining", "name": "Office lunch"}, headers=ALICE)
    assert created.status_code == 201
    sub = created.json()["id"]
    assert client.post("/api/categories/subcategories", json={"group": "Food & Dining", "name": "office LUNCH"},
                       headers=ALICE).status_code == 422          # duplicate
    assert client.post("/api/categories/subcategories", json={"group": "Food & Dining", "name": "Cafes & coffee"},
                       headers=ALICE).status_code == 422          # clashes with the taxonomy
    assert client.post("/api/categories/subcategories", json={"group": "Nope", "name": "x"}, headers=ALICE).status_code == 422
    food = next(g for g in client.get("/api/categories", headers=ALICE).json()["groups"] if g["name"] == "Food & Dining")
    assert {"id": sub, "name": "Office lunch", "custom": True} in food["subcategories"]

    t = client.post("/api/transactions", json=manual(merchant="Canteen", category=None, subcategory=sub), headers=ALICE).json()
    assert (t["category"], t["subcategory"]) == ("Food & Dining", sub)
    # another user can't use, see or delete it
    assert client.post("/api/transactions", json=manual(merchant="x", category=None, subcategory=sub), headers=BOB).status_code == 422
    bob_food = next(g for g in client.get("/api/categories", headers=BOB).json()["groups"] if g["name"] == "Food & Dining")
    assert all(not s.get("custom") for s in bob_food["subcategories"])
    custom_id = sub.split(":", 1)[1]
    assert client.delete(f"/api/categories/subcategories/{custom_id}", headers=BOB).status_code == 404
    # deleting it keeps the group on its transactions
    assert client.delete(f"/api/categories/subcategories/{custom_id}", headers=ALICE).status_code == 204
    t = client.get("/api/transactions", headers=ALICE).json()["items"][0]
    assert (t["category"], t["subcategory"]) == ("Food & Dining", None)


def test_tags_filter_totals_and_isolation(client):
    post(client, [row(), row(description_raw="UPI-ZEPTO-zepto@ybl", amount="200.00", reference="412345678902")])
    items = client.get("/api/transactions", headers=ALICE).json()["items"]
    swiggy = next(t for t in items if t["merchant_clean"] == "Swiggy")
    zepto = next(t for t in items if t["merchant_clean"] == "Zepto")
    r = client.patch(f"/api/transactions/{swiggy['id']}", json={"tags": ["Goa trip", "Reimbursable", "goa  TRIP"]}, headers=ALICE)
    assert r.json()["tags"] == ["Goa trip", "Reimbursable"]
    client.patch(f"/api/transactions/{zepto['id']}", json={"tags": ["goa trip"]}, headers=ALICE)

    listed = client.get("/api/transactions", params={"tag": "GOA TRIP"}, headers=ALICE).json()
    assert {t["id"] for t in listed["items"]} == {swiggy["id"], zepto["id"]}
    assert all(t["tags"] for t in listed["items"])
    tags = client.get("/api/tags", headers=ALICE).json()["items"]
    assert [(t["name"], t["count"]) for t in tags] == [("Goa trip", 2), ("Reimbursable", 1)]

    from app.services import analytics
    from datetime import date
    from tests.conftest import user_session
    with user_session("alice") as (db, user):
        groups = {g["label"]: g["total"] for g in analytics.spend_summary(db, user.id, date(2024, 3, 1), date(2024, 3, 31), "tag")["groups"]}
    assert groups == {"Goa trip": 650, "Reimbursable": 450}

    assert client.get("/api/tags", headers=BOB).json()["items"] == []
    assert client.get("/api/transactions", params={"tag": "Goa trip"}, headers=BOB).json()["total"] == 0
    assert client.delete(f"/api/tags/{tags[0]['id']}", headers=BOB).status_code == 404
    # removing the last use deletes the tag
    client.patch(f"/api/transactions/{swiggy['id']}", json={"tags": ["Goa trip"]}, headers=ALICE)
    assert [t["name"] for t in client.get("/api/tags", headers=ALICE).json()["items"]] == ["Goa trip"]
    assert client.delete(f"/api/tags/{tags[0]['id']}", headers=ALICE).status_code == 204
    assert client.get("/api/transactions", headers=ALICE).json()["items"][0]["tags"] == []


def test_subcategory_budgets(client):
    post(client, [row(date="2024-03-05"), row(description_raw="UPI-STARBUCKS-starbucks@ybl", amount="300.00",
                                              reference="412345678902")])
    assert client.post("/api/budgets", json={"category": "Food & Dining", "subcategory": "food.delivery", "monthly_limit": "400"},
                       headers=ALICE).status_code == 201
    assert client.post("/api/budgets", json={"category": "Travel", "subcategory": "food.delivery", "monthly_limit": "400"},
                       headers=ALICE).status_code == 422
    assert client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "1000"}, headers=ALICE).status_code == 201
    from app.services import analytics
    from datetime import date
    from tests.conftest import user_session
    with user_session("alice") as (db, user):
        status = analytics.budget_status(db, user.id, date(2024, 3, 1))
    lines = {(l["category"], l.get("subcategory")): (l["spent"], l["over"]) for l in status["categories"]}
    assert lines == {("Food & Dining", None): (750, False), ("Food delivery", "food.delivery"): (450, True)}
    listed = client.get("/api/budgets", headers=ALICE).json()
    assert listed["total_monthly_limit"] == "1000.00"     # the subcategory budget sits inside its group's


def test_chat_tools_filter_and_total_by_tag(client, monkeypatch):
    import json as _json
    from tests.test_chat import FakeLLM, call, say
    from app.services import llm
    post(client, [row(), row(description_raw="UPI-ZEPTO-zepto@ybl", amount="200.00", reference="412345678902")])
    swiggy = next(t for t in client.get("/api/transactions", headers=ALICE).json()["items"] if t["merchant_clean"] == "Swiggy")
    client.patch(f"/api/transactions/{swiggy['id']}", json={"tags": ["Goa trip"]}, headers=ALICE)
    f = FakeLLM(call("search_transactions", tag="goa trip"),
                call("spend_summary", start="2024-03-01", end="2024-03-31", group_by="tag"), say("₹450 on the Goa trip."))
    monkeypatch.setattr(llm, "complete", f)
    assert client.post("/api/chat", json={"message": "What did the Goa trip cost?"}, headers=ALICE).status_code == 200
    found, totals = [_json.loads(m["content"]) for m in f.calls[-1]["messages"] if m["role"] == "tool"]
    assert [(t["merchant"], t["tags"], t["subcategory"]) for t in found["transactions"]] == [("Swiggy", ["Goa trip"], "Food delivery")]
    assert [(g["label"], g["total"]) for g in totals["groups"]] == [("Goa trip", "450.00")]
