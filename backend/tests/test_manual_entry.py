import uuid

from tests.conftest import as_user
from tests.test_import_batch import row

ALICE = as_user("alice")


def manual(**overrides):
    return {"client_id": str(uuid.uuid4()), "date": "2024-03-05", "amount": "150", "merchant": "Auto",
            "category": "Transport", "payment_method": "cash", **overrides}


def test_manual_entry_is_normalized_and_idempotent(client):
    body = manual(merchant="swiggy dinner", category=None, amount="450.5")
    first = client.post("/api/transactions", json=body, headers=ALICE)
    assert first.status_code == 201, first.text
    txn = first.json()
    assert (txn["source"], txn["merchant_clean"], txn["category"], txn["amount"]) == ("manual", "Swiggy", "Food & Dining", "450.50")
    assert txn["transaction_nature"] == "expense"
    # double submit with the same client_id → same transaction
    assert client.post("/api/transactions", json=body, headers=ALICE).json()["id"] == txn["id"]
    assert client.get("/api/transactions", headers=ALICE).json()["total"] == 1


def test_user_category_wins_and_income(client):
    txn = client.post("/api/transactions", json=manual(merchant="Mom", category="Other", direction="credit", amount="2000"),
                      headers=ALICE).json()
    assert (txn["category"], txn["transaction_nature"], txn["merchant_clean"]) == ("Other", "income", "Mom")


def test_manual_validation(client):
    for bad in [manual(category="Bribes"), manual(amount=150), manual(amount="0"), manual(date="05-03-2024"),
                manual(source="csv"), manual(merchant=""), manual(notes="acct 50100123456789")]:
        assert client.post("/api/transactions", json=bad, headers=ALICE).status_code == 422, bad


def test_patch_category_and_notes(client):
    txn = client.post("/api/transactions", json=manual(), headers=ALICE).json()
    res = client.patch(f"/api/transactions/{txn['id']}", json={"category": "Travel", "notes": "airport"}, headers=ALICE)
    assert res.status_code == 200, res.text
    assert (res.json()["category"], res.json()["notes"], res.json()["user_corrected"]) == ("Travel", "airport", "true")
    # notes-only change leaves category alone; null clears category
    assert client.patch(f"/api/transactions/{txn['id']}", json={"notes": None}, headers=ALICE).json()["category"] == "Travel"
    assert client.patch(f"/api/transactions/{txn['id']}", json={"category": None}, headers=ALICE).json()["category"] is None
    for bad in [{}, {"category": "Nope"}, {"amount": "1.00"}]:
        assert client.patch(f"/api/transactions/{txn['id']}", json=bad, headers=ALICE).status_code == 422, bad


def test_delete_manual_only(client):
    txn = client.post("/api/transactions", json=manual(), headers=ALICE).json()
    assert client.delete(f"/api/transactions/{txn['id']}", headers=ALICE).status_code == 204
    assert client.get("/api/transactions", headers=ALICE).json()["total"] == 0

    client.post("/api/import/batch", json={"rows": [row()]}, headers=ALICE)
    imported = client.get("/api/transactions", headers=ALICE).json()["items"][0]
    assert client.delete(f"/api/transactions/{imported['id']}", headers=ALICE).status_code == 409


def test_manual_entry_later_matched_by_statement_cannot_be_deleted(client):
    txn = client.post("/api/transactions", json=manual(merchant="Zepto", amount="382", category=None), headers=ALICE).json()
    res = client.post("/api/import/batch", json={"rows": [row(description_raw="UPI-ZEPTO-zepto@ybl-XXXX", amount="382.00", reference=None)]},
                      headers=ALICE).json()
    assert res["duplicates_merged"] == 1
    assert client.delete(f"/api/transactions/{txn['id']}", headers=ALICE).status_code == 409


def test_unknown_id_is_404(client):
    missing = uuid.uuid4()
    assert client.patch(f"/api/transactions/{missing}", json={"notes": "x"}, headers=ALICE).status_code == 404
    assert client.delete(f"/api/transactions/{missing}", headers=ALICE).status_code == 404
