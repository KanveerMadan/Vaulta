"""Delete this import and Reset my data (services/imports.py): what goes, what stays, recomputing, and isolation."""

import uuid

from sqlalchemy import text

from tests.conftest import as_user, owner_engine

ALICE, BOB = as_user("alice"), as_user("bob")
UTR = "412345678901"


def bank(**kw):
    return {"date": "2026-07-03", "description_raw": "UPI/RAHUL KUMAR/pay", "amount": "500.00",
            "direction": "debit", "reference": UTR, "source_type": "bank_pdf", "source_label": "Kotak Mahindra Bank",
            "type": "transaction", **kw}


def gpay(**kw):
    return {"date": "2026-07-03T10:30:00", "description_raw": "Rahul Kumar", "amount": "500.00", "direction": "debit",
            "reference": UTR, "source_type": "upi_google_pay", "source_label": "Google Pay", "type": "transaction", **kw}


def upload(client, rows, headers=ALICE, import_id=None):
    import_id = import_id or str(uuid.uuid4())
    res = client.post("/api/import/batch", json={"rows": rows, "import_id": import_id}, headers=headers)
    assert res.status_code == 200, res.text
    return import_id


def total(client, headers=ALICE):
    return client.get("/api/transactions", headers=headers).json()["total"]


def test_deleting_an_upload_keeps_what_another_statement_also_shows(client):
    k = upload(client, [bank(), bank(date="2026-07-04", description_raw="SWIGGY ORDER", reference=None, amount="250.00")])
    g = upload(client, [gpay(), gpay(date="2026-07-05T09:00:00", description_raw="Chai Point", reference="499999999999",
                                     amount="20.00")])
    assert total(client) == 3                                   # the shared payment merged
    listed = client.get("/api/import/uploads", headers=ALICE).json()
    assert {u["id"]: u["rows"] for u in listed["uploads"]} == {k: 2, g: 2}

    preview = client.post("/api/import/delete-preview", json={"import_id": g}, headers=ALICE).json()
    assert preview == {"source_rows": 2, "transactions_deleted": 1, "transactions_kept": 1}
    res = client.post("/api/import/delete", json={"import_id": g}, headers=ALICE).json()
    assert res["transactions_deleted"] == 1 and res["transactions_kept"] == 1
    assert total(client) == 2
    assert [u["id"] for u in client.get("/api/import/uploads", headers=ALICE).json()["uploads"]] == [k]

    upload(client, [gpay()])                                    # importing it again merges again
    assert total(client) == 2
    assert "import_deleted" in [e["kind"] for e in client.get("/api/activity", headers=ALICE).json()]


def test_deleting_a_source_covers_rows_from_before_uploads_were_recorded(client):
    client.post("/api/import/batch", json={"rows": [bank(reference=None), bank(date="2026-07-09", reference=None)]},
                headers=ALICE)                                  # no import_id: an old import
    upload(client, [gpay(reference="477777777777", date="2026-08-01T10:00:00")])
    scope = {"source_type": "bank_pdf", "source_label": "Kotak Mahindra Bank"}
    assert client.post("/api/import/delete-preview", json=scope, headers=ALICE).json()["transactions_deleted"] == 2
    client.post("/api/import/delete", json=scope, headers=ALICE)
    assert total(client) == 1


def test_transfers_and_people_are_recomputed(client):
    # the same 5,000 leaving one account and arriving in another: a transfer pair while both legs are there
    a = upload(client, [bank(description_raw="NEFT OUT", reference=None, amount="5000.00")])
    b = upload(client, [bank(description_raw="NEFT IN", reference=None, amount="5000.00",
                             direction="credit", source_type="bank_csv", source_label="HDFC Bank")])
    kinds = lambda: sorted(t["kind"] for t in client.get("/api/transactions", headers=ALICE).json()["items"])  # noqa: E731
    assert kinds() == ["transfer", "transfer"]
    client.post("/api/import/delete", json={"import_id": b}, headers=ALICE)
    assert kinds() == ["spend"]                                 # one leg alone is spending: detection ran again
    # a person only this upload showed goes with it
    p = upload(client, [gpay(reference="466666666666", description_raw="Priya Sharma", date="2026-08-02T10:00:00")])
    people = lambda: [x["name"] for x in client.get("/api/people", headers=ALICE).json()["people"]]  # noqa: E731
    assert any("Priya" in n for n in people())
    assert client.post("/api/import/delete", json={"import_id": p}, headers=ALICE).json()["people_removed"] >= 1
    assert not any("Priya" in n for n in people())
    assert a


def test_another_users_upload_is_out_of_reach(client):
    g = upload(client, [gpay()])
    upload(client, [bank(reference=None, description_raw="BOB SHOP")], headers=BOB)
    assert [u["id"] for u in client.get("/api/import/uploads", headers=BOB).json()["uploads"]] != [g]
    assert g not in str(client.get("/api/import/uploads", headers=BOB).json())
    for path in ("/api/import/delete-preview", "/api/import/delete"):
        assert client.post(path, json={"import_id": g}, headers=BOB).status_code == 404
    # nor can bob attach rows to alice's upload id
    res = client.post("/api/import/batch", json={"rows": [bank(reference=None)], "import_id": g}, headers=BOB)
    assert res.status_code == 409
    scope = {"source_type": "upi_google_pay", "source_label": "Google Pay"}
    assert client.post("/api/import/delete", json=scope, headers=BOB).status_code == 404
    assert total(client) == 1 and total(client, BOB) == 1


def test_scope_must_be_one_thing(client):
    for body in ({}, {"import_id": str(uuid.uuid4()), "source_type": "bank_pdf"}, {"import_id": "not-a-uuid"}):
        assert client.post("/api/import/delete-preview", json=body, headers=ALICE).status_code == 422


def test_reset_my_data_keeps_the_account_and_touches_no_one_else(client):
    upload(client, [bank(), gpay(reference="455555555555", date="2026-08-03T10:00:00")])
    client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "3000"}, headers=ALICE)
    upload(client, [bank(reference=None, description_raw="BOB SHOP")], headers=BOB)
    client.post("/api/budgets", json={"category": "Travel", "monthly_limit": "100"}, headers=BOB)
    assert client.post("/auth/me/reset-data", json={"confirm": "yes"}, headers=ALICE).status_code == 400
    res = client.post("/auth/me/reset-data", json={"confirm": "RESET"}, headers=ALICE)
    assert res.status_code == 200 and res.json()["deleted"]["transactions"] == 2

    assert client.get("/auth/me", headers=ALICE).status_code == 200           # still signed in, same account
    assert total(client) == 0
    with owner_engine.connect() as conn:
        alice, bob = (conn.execute(text("SELECT id FROM users WHERE firebase_uid = :u"), {"u": u}).scalar() for u in ("alice", "bob"))
        mine = lambda t, u: conn.execute(text(f"SELECT count(*) FROM {t} WHERE user_id = :u"), {"u": u}).scalar()  # noqa: E731
        for table in ("transactions", "transaction_sources", "imports", "budgets", "people"):
            assert mine(table, alice) == 0, table
        assert mine("transactions", bob) == 1 and mine("budgets", bob) == 1    # bob untouched
        assert mine("activity_log", alice) >= 1                               # the log stays, with the reset in it
        assert conn.execute(text("SELECT count(*) FROM activity_log WHERE user_id = :u AND kind = 'data_reset'"),
                            {"u": alice}).scalar() == 1
    upload(client, [bank()])                                                  # and the account works afterwards
    assert total(client) == 1
