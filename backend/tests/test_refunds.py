"""Refunds (full, partial, unmatched) and failed-UPI reversals."""

from tests.conftest import as_user
from tests.test_import_batch import row

ALICE = as_user("alice")
MARCH = "/api/transactions/summary?period=month&year=2024&month=3"


def load(client, *rows):
    if rows:
            assert client.post("/api/import/batch", json={"rows": list(rows)}, headers=ALICE).status_code == 200
    items = client.get("/api/transactions?page_size=200", headers=ALICE).json()["items"]
    return {(t["merchant_raw"], t["transaction_date"][:10]): t for t in items}


def r(date, desc, amount, direction="debit", ref=None, **kw):
    return row(date=date, description_raw=desc, amount=amount, direction=direction, reference=ref, **kw)


def food(client):
    return {c["category"]: c["total"] for c in client.get(MARCH, headers=ALICE).json()["categories"]}


def test_full_refund_from_same_merchant(client):
    t = load(client, r("2024-03-02", "AMAZON PAY INDIA ORDER", "1999.00"),
             r("2024-03-09", "AMAZON PAY INDIA", "1999.00", "credit"))
    refund, original = t[("AMAZON PAY INDIA", "2024-03-09")], t[("AMAZON PAY INDIA ORDER", "2024-03-02")]
    assert (refund["kind"], refund["refund_of_id"], refund["category"]) == ("refund", original["id"], original["category"])
    summary = client.get(MARCH, headers=ALICE).json()
    assert summary["total_spend"] == "0.00" and summary["total_received"] == "0.00"


def test_partial_refunds_net_and_cannot_exceed_original(client):
    t = load(client, r("2024-03-01", "SWIGGY ORDER", "1000.00"),
             r("2024-03-03", "SWIGGY REFUND", "300.00", "credit"),
             r("2024-03-05", "SWIGGY REFUND", "500.00", "credit"),
             r("2024-03-06", "SWIGGY", "400.00", "credit"))       # only 200 left of the 1000
    original = t[("SWIGGY ORDER", "2024-03-01")]
    assert t[("SWIGGY REFUND", "2024-03-03")]["refund_of_id"] == original["id"]
    assert t[("SWIGGY REFUND", "2024-03-05")]["refund_of_id"] == original["id"]
    assert t[("SWIGGY", "2024-03-06")]["kind"] == "income"           # exceeds what's left, no refund wording
    assert food(client)["Food & Dining"] == "200.00"


def test_unmatched_refund_wording_still_refund(client):
    t = load(client, r("2024-03-10", "NEFT RFND IRCTC TKT 4471", "845.00", "credit"))
    refund = t[("NEFT RFND IRCTC TKT 4471", "2024-03-10")]
    assert (refund["kind"], refund["refund_of_id"]) == ("refund", None)
    assert client.get(MARCH, headers=ALICE).json()["total_received"] == "0.00"


def test_refund_outside_60_days_or_other_merchant_is_not_linked(client):
    t = load(client, r("2024-01-01", "ZOMATO ORDER", "600.00"),
             r("2024-03-05", "ZOMATO", "600.00", "credit"),          # 64 days later
             r("2024-03-06", "BLINKIT", "600.00", "credit"))         # different merchant
    assert t[("ZOMATO", "2024-03-05")]["kind"] == "income"
    assert t[("BLINKIT", "2024-03-06")]["kind"] == "income"


def test_failed_upi_same_utr_is_reversal_on_both_sides(client):
    t = load(client, r("2024-03-04", "UPI-ZEPTO-zepto@ybl-Grocery", "382.00", ref="412399990000"),
             r("2024-03-04", "UPI-ZEPTO-zepto@ybl", "382.00", "credit", ref="412399990000"))
    debit, credit = t[("UPI-ZEPTO-zepto@ybl-Grocery", "2024-03-04")], t[("UPI-ZEPTO-zepto@ybl", "2024-03-04")]
    assert debit["kind"] == credit["kind"] == "reversal" and credit["refund_of_id"] == debit["id"]
    summary = client.get(MARCH, headers=ALICE).json()
    assert summary["total_spend"] == "0.00" and summary["total_received"] == "0.00"


def test_failed_upi_by_narration_within_7_days(client):
    t = load(client, r("2024-03-04", "UPI-RAJU-R***@ybl-tea", "50.00"),
             r("2024-03-09", "UPI REV 412 RAJU", "50.00", "credit"),
             r("2024-03-10", "SHOP", "70.00"),
             r("2024-03-20", "UPI REVERSAL 413", "70.00", "credit"))   # 10 days later: not a reversal → refund by wording
    assert t[("UPI-RAJU-R***@ybl-tea", "2024-03-04")]["kind"] == "reversal"
    assert t[("UPI REV 412 RAJU", "2024-03-09")]["kind"] == "reversal"
    assert t[("SHOP", "2024-03-10")]["kind"] == "spend"
    assert t[("UPI REVERSAL 413", "2024-03-20")]["kind"] == "refund"


def test_refund_links_follow_user_corrections(client):
    t = load(client, r("2024-03-02", "AMAZON PAY INDIA ORDER", "1999.00"),
             r("2024-03-09", "AMAZON PAY INDIA", "1999.00", "credit"))
    refund = t[("AMAZON PAY INDIA", "2024-03-09")]
    client.patch(f"/api/transactions/{refund['id']}", json={"kind": "income"}, headers=ALICE)
    after = load(client)[("AMAZON PAY INDIA", "2024-03-09")]
    assert (after["kind"], after["refund_of_id"]) == ("income", None)
    assert client.get(MARCH, headers=ALICE).json()["total_spend"] == "1999.00"
