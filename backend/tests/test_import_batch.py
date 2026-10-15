from tests.conftest import as_user

ALICE = as_user("alice")


def row(**overrides):
    base = {
        "date": "2024-03-05",
        "description_raw": "UPI-SWIGGY-swiggy.rzp@axisbank-XXXX-Payment",
        "amount": "450.00",
        "direction": "debit",
        "reference": "412345678901",
        "source_type": "bank_csv",
        "source_label": "HDFC Bank",
        "type": "transaction",
    }
    return {**base, **overrides}


def post(client, rows, headers=ALICE):
    return client.post("/api/import/batch", json={"rows": rows}, headers=headers)


def test_imports_rows_through_normalizer(client):
    res = post(client, [
        row(),
        row(date="2024-03-07", description_raw="NEFT CR-ACME CORP PAYROLL-XXXX", amount="85000.00",
            direction="credit", reference="N123456789"),
        row(date="2024-03-08", description_raw="SOME LOCAL SHOP", amount="120.00", reference=None),
    ])
    assert res.status_code == 200, res.text
    assert res.json() == {"imported": 3, "duplicates_merged": 0, "transfers_flagged": 0, "rows_needing_review": 2, "failed": 0}

    items = client.get("/api/transactions", headers=ALICE).json()["items"]
    by_amount = {i["amount"]: i for i in items}
    assert by_amount["450.00"]["merchant_clean"] == "Swiggy"
    assert by_amount["450.00"]["category"] == "Food & Dining"
    assert by_amount["450.00"]["transaction_nature"] == "expense"
    assert by_amount["85000.00"]["transaction_nature"] == "income"
    assert by_amount["120.00"]["category"] is None


def test_reimport_and_cross_source_utr_match_are_merged(client):
    assert post(client, [row()]).json()["imported"] == 1
    # same file again
    assert post(client, [row()]).json() == {"imported": 0, "duplicates_merged": 1, "transfers_flagged": 0, "rows_needing_review": 0, "failed": 0}
    # the same payment seen in a Google Pay statement (UTR match, tier 1)
    gpay = row(date="2024-03-05T13:05:00", description_raw="Swiggy", source_type="upi_google_pay", source_label="Google Pay")
    assert post(client, [gpay]).json()["duplicates_merged"] == 1
    assert client.get("/api/transactions", headers=ALICE).json()["total"] == 1


def test_identical_rows_in_one_batch_are_both_kept(client):
    chai = row(description_raw="CHAI POINT", amount="20.00", reference=None)
    assert post(client, [chai, chai]).json()["imported"] == 2


def test_transfers_and_upi_peer_payments(client):
    res = post(client, [
        row(description_raw="PAYMENT RECEIVED - THANK YOU", amount="15000.00", direction="credit",
            reference=None, source_type="credit_card", source_label="HDFC Bank Credit Card", type="transfer"),
        row(date="2026-05-05T21:10:00", description_raw="Rahul Sharma", amount="1500.00", direction="credit",
            reference="612456562368", source_type="upi_google_pay", source_label="Google Pay"),
    ]).json()
    assert res["transfers_flagged"] == 1
    natures = {i["merchant_raw"]: (i["transaction_nature"], i["category"])
               for i in client.get("/api/transactions", headers=ALICE).json()["items"]}
    assert natures["PAYMENT RECEIVED - THANK YOU"][0] == "self_transfer"
    assert natures["Rahul Sharma"] == ("peer_payment_received", "Received from People")


def test_rejects_unexpected_fields_and_account_numbers(client):
    cases = [
        row(balance="1,23,456.78"),                                 # extra field
        row(account_number="50100123456789"),                       # extra field
        row(description_raw="NEFT-RAHUL-50100123456789"),           # account number in text
        row(reference="50100123456789"),                            # account number as reference
        row(amount=450),                                            # not a string (strict)
        row(amount="450"),                                          # not 2dp
        row(amount="0.00"),
        row(date="05/03/2024"),
        row(date="2024-02-30"),
        row(direction="out"),
        row(source_type="gmail"),
        row(description_raw="x" * 201),
    ]
    for bad in cases:
        assert post(client, [bad]).status_code == 422, bad
    assert client.post("/api/import/batch", json={"rows": [row()], "file": "data"}, headers=ALICE).status_code == 422
    assert post(client, []).status_code == 422
    assert post(client, [row()] * 501).status_code == 422
    assert client.get("/api/transactions", headers=ALICE).json()["total"] == 0


def test_file_upload_endpoint_is_gone(client):
    res = client.post("/api/statements/upload", files={"file": ("s.csv", b"a,b\n1,2\n")}, headers=ALICE)
    assert res.status_code == 404


def test_requires_auth(client):
    assert client.post("/api/import/batch", json={"rows": [row()]}).status_code in (401, 403)


def test_mapping_templates_round_trip(client):
    fp = "a" * 64
    mapping = {"date": 0, "description": 1, "debit": None, "credit": None, "amount": 2, "reference": 3,
               "date_format": "%d-%m-%Y", "amount_sign": "negative_is_debit"}
    assert client.get(f"/api/import/templates/{fp}", headers=ALICE).status_code == 404
    put = client.put(f"/api/import/templates/{fp}", json={"column_count": 4, "source_type": "bank_csv", "mapping": mapping}, headers=ALICE)
    assert put.status_code == 200, put.text
    got = client.get(f"/api/import/templates/{fp}", headers=ALICE).json()
    assert got["mapping"] == mapping and got["column_count"] == 4
    # per-user
    assert client.get(f"/api/import/templates/{fp}", headers=as_user("bob")).status_code == 404
    # no room for transaction data
    bad = {"column_count": 4, "source_type": "bank_csv", "mapping": {**mapping, "sample": "UPI-RAHUL"}}
    assert client.put(f"/api/import/templates/{fp}", json=bad, headers=ALICE).status_code == 422
    assert client.get("/api/import/templates/not-a-fingerprint", headers=ALICE).status_code == 422


def test_fuzzy_cross_source_match_still_merges(client):
    # No shared UTR: bank narration vs PhonePe counterparty, same day/amount/direction
    assert post(client, [row(description_raw="UPI-ZEPTO-zepto@ybl-XXXX-Grocery", amount="382.00", reference=None)]).json()["imported"] == 1
    phonepe = row(date="2024-03-05T08:15:00", description_raw="Zepto Marketplace", amount="382.00",
                  reference="T2403050815123456789", source_type="upi_phonepe", source_label="PhonePe")
    assert post(client, [phonepe]).json()["duplicates_merged"] == 1
    assert client.get("/api/transactions", headers=ALICE).json()["total"] == 1
