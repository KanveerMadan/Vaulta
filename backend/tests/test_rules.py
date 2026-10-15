"""Learned rules (services/rules.py) and /api/rules."""

from tests.conftest import as_user
from tests.test_import_batch import row

ALICE, BOB = as_user("alice"), as_user("bob")


def chai(day, amount="40.00"):
    return row(date=f"2024-03-{day:02d}", description_raw="CHAI POINT KORAMANGALA", amount=amount, reference=None)


def load(client, *rows):
    if rows:
        assert client.post("/api/import/batch", json={"rows": list(rows)}, headers=ALICE).status_code == 200
    return client.get("/api/transactions?page_size=200", headers=ALICE).json()["items"]


def categorize(client, txn, category):
    res = client.patch(f"/api/transactions/{txn['id']}", json={"category": category}, headers=ALICE)
    assert res.status_code == 200, res.text
    return res.json()


def test_two_consistent_corrections_learn_a_rule(client):
    txns = load(client, *[chai(d) for d in range(1, 7)])
    assert {t["category"] for t in txns} == {None}
    assert categorize(client, txns[0], "Food & Dining")["rule_applied"] is None     # one correction: no rule yet
    second = categorize(client, txns[1], "Food & Dining")
    assert second["rule_applied"]["applied_count"] == 4
    assert second["rule_applied"]["field"] == "category" and second["rule_applied"]["value"] == "Food & Dining"
    assert {t["category"] for t in load(client)} == {"Food & Dining"}
    # future transactions from the merchant follow the rule
    assert {t["category"] for t in load(client, chai(20, "55.00"))} == {"Food & Dining"}

    rules = client.get("/api/rules", headers=ALICE).json()["rules"]
    assert [(r["merchant_key"], r["field"], r["value"], r["origin"], r["matches"]) for r in rules] == [
        ("chai point koramangala", "category", "Food & Dining", "learned", 7)]

    # Undo: auto values come back; the two corrected transactions keep the user's value
    assert client.delete(f"/api/rules/{rules[0]['id']}", headers=ALICE).status_code == 204
    cats = sorted((t["category"] or "") for t in load(client))
    assert cats == ["", "", "", "", "", "Food & Dining", "Food & Dining"]


def test_inconsistent_corrections_learn_nothing_and_individual_overrides_win(client):
    txns = load(client, *[chai(d) for d in range(1, 5)])
    categorize(client, txns[0], "Food & Dining")
    assert categorize(client, txns[1], "Groceries")["rule_applied"] is None
    assert categorize(client, txns[2], "Groceries")["rule_applied"]["applied_count"] == 1   # only txns[3] was uncorrected
    by_id = {t["id"]: t["category"] for t in load(client)}
    assert by_id[txns[0]["id"]] == "Food & Dining"      # its own correction stands


def test_kind_rule(client):
    rows = [row(date=f"2024-03-{d:02d}", description_raw="CRED CLUB BILL", amount="5000.00", reference=None) for d in (1, 8, 15)]
    txns = load(client, *rows)
    client.patch(f"/api/transactions/{txns[0]['id']}", json={"kind": "transfer"}, headers=ALICE)
    res = client.patch(f"/api/transactions/{txns[1]['id']}", json={"kind": "transfer"}, headers=ALICE).json()
    assert res["rule_applied"]["field"] == "kind" and res["rule_applied"]["applied_count"] == 1
    assert {t["kind"] for t in load(client)} == {"transfer"}
    assert client.get("/api/transactions/summary?period=month&year=2024&month=3", headers=ALICE).json()["total_spend"] == "0.00"


def test_manual_rule_edit_and_validation(client):
    load(client, *[chai(d) for d in (1, 2)])
    res = client.post("/api/rules", json={"merchant_key": "chai point koramangala", "merchant": "Chai Point",
                                          "field": "category", "value": "Food & Dining"}, headers=ALICE)
    assert res.status_code == 201 and res.json()["matches"] == 2
    rid = res.json()["id"]
    assert {t["category"] for t in load(client)} == {"Food & Dining"}
    assert client.patch(f"/api/rules/{rid}", json={"value": "Groceries"}, headers=ALICE).json()["value"] == "Groceries"
    assert {t["category"] for t in load(client)} == {"Groceries"}
    for bad in [{"value": "Bribes"}, {"value": ""}, {}]:
        assert client.patch(f"/api/rules/{rid}", json=bad, headers=ALICE).status_code == 422
    bad_create = {"merchant_key": "x", "merchant": "x", "field": "kind", "value": "gift"}
    assert client.post("/api/rules", json=bad_create, headers=ALICE).status_code == 422


def test_rules_are_per_user(client):
    load(client, *[chai(d) for d in (1, 2)])
    rid = client.post("/api/rules", json={"merchant_key": "chai point koramangala", "merchant": "Chai Point",
                                          "field": "category", "value": "Food & Dining"}, headers=ALICE).json()["id"]
    assert client.get("/api/rules", headers=BOB).json() == {"rules": []}
    assert client.patch(f"/api/rules/{rid}", json={"value": "Groceries"}, headers=BOB).status_code == 404
    assert client.delete(f"/api/rules/{rid}", headers=BOB).status_code == 404
    # Bob's rule for the same merchant doesn't touch Alice's transactions
    client.post("/api/rules", json={"merchant_key": "chai point koramangala", "merchant": "Chai Point",
                                    "field": "category", "value": "Shopping"}, headers=BOB)
    assert {t["category"] for t in load(client)} == {"Food & Dining"}
