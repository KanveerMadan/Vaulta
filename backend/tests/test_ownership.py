"""
A user cannot read, edit or delete another user's data through any route.
test_every_route_is_covered fails if a user-data route is added without a
case here.
"""

import uuid

from fastapi.routing import APIRoute

from app.main import app
from tests.conftest import as_user
from tests.test_import_batch import row
from tests.test_manual_entry import manual

ALICE, BOB = as_user("alice"), as_user("bob")

COVERED = {
    ("GET", "/api/transactions"),
    ("GET", "/api/transactions/summary"),
    ("POST", "/api/transactions"),
    ("POST", "/api/transactions/reanalyze"),
    ("PATCH", "/api/transactions/{transaction_id}"),
    ("DELETE", "/api/transactions/{transaction_id}"),
    ("POST", "/api/import/batch"),
    ("GET", "/api/import/templates/{fingerprint}"),
    ("PUT", "/api/import/templates/{fingerprint}"),
    ("GET", "/api/recurring"),
    ("PATCH", "/api/recurring/{series_id}"),
    ("POST", "/api/recurring/refresh"),
}
GUARDED_PREFIXES = ("/api/transactions", "/api/import", "/api/recurring")


def test_every_route_is_covered():
    routes = {
        (method, r.path)
        for r in app.routes if isinstance(r, APIRoute) and r.path.startswith(GUARDED_PREFIXES)
        for method in r.methods
    }
    assert routes == COVERED


def _alice_data(client):
    manual_txn = client.post("/api/transactions", json=manual(client_id="11111111-1111-1111-1111-111111111111"),
                             headers=ALICE).json()
    client.post("/api/import/batch", json={"rows": [row()]}, headers=ALICE)
    items = client.get("/api/transactions", headers=ALICE).json()["items"]
    assert len(items) == 2
    return manual_txn, next(i for i in items if i["id"] != manual_txn["id"])


def test_bob_cannot_read_alice(client):
    _alice_data(client)
    assert client.get("/api/transactions", headers=BOB).json() == {"items": [], "total": 0, "page": 1, "page_size": 50, "has_more": False}
    for period in ("month", "year", "lifetime"):
        summary = client.get(f"/api/transactions/summary?period={period}&year=2024&month=3", headers=BOB).json()
        assert summary["transaction_count"] == 0 and summary["total_spend"] == "0.00", period


def test_bob_cannot_edit_or_delete_alice(client):
    manual_txn, imported = _alice_data(client)
    for txn in (manual_txn, imported):
        assert client.patch(f"/api/transactions/{txn['id']}", json={"category": "Travel", "notes": "bob"}, headers=BOB).status_code == 404
        assert client.delete(f"/api/transactions/{txn['id']}", headers=BOB).status_code == 404
    after = {i["id"]: i for i in client.get("/api/transactions", headers=ALICE).json()["items"]}
    assert after[manual_txn["id"]]["category"] == "Transport" and after[manual_txn["id"]]["notes"] is None
    assert after[imported["id"]]["user_corrected"] is None
    assert len(after) == 2


def test_bob_cannot_reach_alice_through_ingestion(client):
    manual_txn, imported = _alice_data(client)
    # Same client_id as Alice's manual entry → Bob gets his own row, not hers
    bobs = client.post("/api/transactions", json=manual(client_id="11111111-1111-1111-1111-111111111111"), headers=BOB).json()
    assert bobs["id"] != manual_txn["id"] and bobs["user_id"] != manual_txn["user_id"]
    # Same UTR / same content as Alice's import → not merged into her transaction
    assert client.post("/api/import/batch", json={"rows": [row()]}, headers=BOB).json()["imported"] == 1
    assert client.get("/api/transactions", headers=ALICE).json()["total"] == 2
    assert client.get("/api/transactions", headers=BOB).json()["total"] == 2


def test_bob_cannot_read_alice_templates(client):
    fp = "b" * 64
    body = {"column_count": 3, "source_type": "bank_csv", "mapping": {
        "date": 0, "description": 1, "amount": 2, "date_format": "%d/%m/%Y", "amount_sign": "negative_is_debit"}}
    assert client.put(f"/api/import/templates/{fp}", json=body, headers=ALICE).status_code == 200
    assert client.get(f"/api/import/templates/{fp}", headers=BOB).status_code == 404
    # Bob writing the same fingerprint creates his own, Alice's is unchanged
    client.put(f"/api/import/templates/{fp}", json={**body, "column_count": 9}, headers=BOB)
    assert client.get(f"/api/import/templates/{fp}", headers=ALICE).json()["column_count"] == 3


def test_random_ids_are_404(client):
    _alice_data(client)
    assert client.patch(f"/api/transactions/{uuid.uuid4()}", json={"notes": "x"}, headers=ALICE).status_code == 404


def test_bob_reanalyze_leaves_alice_alone(client):
    manual_txn, imported = _alice_data(client)
    client.patch(f"/api/transactions/{imported['id']}", json={"kind": "lent"}, headers=ALICE)
    before = client.get("/api/transactions", headers=ALICE).json()["items"]
    assert client.post("/api/transactions/reanalyze", headers=BOB).status_code == 204
    assert client.get("/api/transactions", headers=ALICE).json()["items"] == before


def test_bob_cannot_see_or_change_alice_recurring(client):
    from datetime import date
    from app.services.recurring import add_months
    rows = [row(date=add_months(date.today(), -k).isoformat(), description_raw="NETFLIX COM", amount="649.00", reference=None)
            for k in (2, 1, 0)]
    client.post("/api/import/batch", json={"rows": rows}, headers=ALICE)
    series = client.get("/api/recurring", headers=ALICE).json()["series"]
    assert len(series) == 1
    assert client.get("/api/recurring", headers=BOB).json() == {"series": [], "monthly_committed": "0.00", "upcoming": []}
    assert client.patch(f"/api/recurring/{series[0]['id']}", json={"user_status": "dismissed"}, headers=BOB).status_code == 404
    client.post("/api/recurring/refresh", headers=BOB)
    assert client.get("/api/recurring", headers=ALICE).json()["series"] == series
