"""Only kind=spend (net of refunds) is spending and only kind=income is income."""

from tests.conftest import as_user
from tests.test_import_batch import row

ALICE = as_user("alice")
SUMMARY = "/api/transactions/summary?period=month&year=2024&month=3"


def imported(client, *rows):
    assert client.post("/api/import/batch", json={"rows": list(rows)}, headers=ALICE).status_code == 200
    return {t["merchant_raw"]: t for t in client.get("/api/transactions", headers=ALICE).json()["items"]}


def set_kind(client, txn, kind, expect=200):
    res = client.patch(f"/api/transactions/{txn['id']}", json={"kind": kind}, headers=ALICE)
    assert res.status_code == expect, res.text
    return res.json()


def test_default_kinds(client):
    txns = imported(
        client,
        row(description_raw="SWIGGY", reference=None),
        row(description_raw="SALARY ACME", direction="credit", amount="50000.00", reference=None),
        row(description_raw="PAYMENT RECEIVED - THANK YOU", direction="credit", amount="9000.00", reference=None,
            source_type="credit_card", source_label="HDFC Bank Credit Card", type="transfer"),
    )
    assert {k: (t["kind"], t["direction"]) for k, t in txns.items()} == {
        "SWIGGY": ("spend", "debit"),
        "SALARY ACME": ("income", "credit"),
        "PAYMENT RECEIVED - THANK YOU": ("transfer", "credit"),
    }


def test_only_spend_and_income_count(client):
    txns = imported(
        client,
        row(description_raw="SWIGGY", amount="1000.00", reference=None),
        row(description_raw="SWIGGY REFUND", amount="300.00", direction="credit", reference=None),
        row(description_raw="TO OWN SBI", amount="20000.00", reference=None),
        row(description_raw="FROM OWN HDFC", amount="20000.00", direction="credit", reference=None, source_label="SBI"),
        row(description_raw="UPI FAILED", amount="500.00", reference=None),
        row(description_raw="UPI FAILED REV", amount="500.00", direction="credit", reference=None),
        row(description_raw="TO AMIT", amount="2000.00", reference=None),
        row(description_raw="FROM PRIYA", amount="700.00", direction="credit", reference=None),
        row(description_raw="SALARY", amount="50000.00", direction="credit", reference=None),
    )
    before = client.get(SUMMARY, headers=ALICE).json()
    assert (before["total_spend"], before["total_received"]) == ("23500.00", "71500.00")  # everything counted by default

    refund = set_kind(client, txns["SWIGGY REFUND"], "refund")
    client.patch(f"/api/transactions/{refund['id']}", json={"category": "Food & Dining"}, headers=ALICE)
    set_kind(client, txns["TO OWN SBI"], "transfer")
    set_kind(client, txns["FROM OWN HDFC"], "transfer")
    set_kind(client, txns["UPI FAILED"], "reversal")
    set_kind(client, txns["UPI FAILED REV"], "reversal")
    set_kind(client, txns["TO AMIT"], "lent")
    set_kind(client, txns["FROM PRIYA"], "borrowed")

    after = client.get(SUMMARY, headers=ALICE).json()
    assert after["total_spend"] == "700.00"            # 1000 Swiggy − 300 refund
    assert after["total_received"] == "50000.00"       # salary only
    assert after["transaction_count"] == 1
    assert [(c["category"], c["total"]) for c in after["categories"]] == [("Food & Dining", "700.00")]
    assert after["top_merchants"] == [{"merchant_clean": "Swiggy", "total": 700.0, "count": 1}]
    for period in ("year", "lifetime"):
        assert client.get(f"/api/transactions/summary?period={period}&year=2024", headers=ALICE).json()["total_spend"] == "700.00"


def test_budget_consumption_uses_net_spend(client):
    txns = imported(client, row(description_raw="SWIGGY", amount="1000.00", reference=None),
                    row(description_raw="SWIGGY REFUND", amount="400.00", direction="credit", reference=None))
    refund = set_kind(client, txns["SWIGGY REFUND"], "refund")
    client.patch(f"/api/transactions/{refund['id']}", json={"category": "Food & Dining"}, headers=ALICE)
    client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "1200"}, headers=ALICE)
    food = client.get(SUMMARY, headers=ALICE).json()["categories"][0]
    assert (food["total"], food["budget_consumed_pct"]) == ("600.00", "50.0")


def test_kind_patch_validates_direction_and_records_correction(client):
    txns = imported(client, row(description_raw="SWIGGY", reference=None))
    set_kind(client, txns["SWIGGY"], "income", expect=422)    # a debit can't be income
    set_kind(client, txns["SWIGGY"], "refund", expect=422)
    updated = set_kind(client, txns["SWIGGY"], "lent")
    assert (updated["kind"], updated["user_corrected"]) == ("lent", "true")
    assert client.patch(f"/api/transactions/{updated['id']}", json={"kind": None}, headers=ALICE).status_code == 422
    assert client.patch(f"/api/transactions/{updated['id']}", json={"kind": "gift"}, headers=ALICE).status_code == 422
