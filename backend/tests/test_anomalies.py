"""Anomalies (services/anomalies.py) with today pinned to 2024-06-28."""

from tests.conftest import as_user
from tests.test_end_to_end import USER, frozen_today  # noqa: F401 (fixture)
from tests.test_import_batch import row

BOB = as_user("bob")


def r(d, desc, amount, direction="debit", ref=None, **kw):
    return row(date=d, description_raw=desc, amount=amount, direction=direction, reference=ref, **kw)


def gpay(d, desc, amount, ref):
    return r(d, desc, amount, ref=ref, source_type="upi_google_pay", source_label="Google Pay")


def load(client, *rows):
    if rows:
        assert client.post("/api/import/batch", json={"rows": list(rows)}, headers=USER).status_code == 200
    return {a["type"]: a for a in client.get("/api/anomalies", headers=USER).json()}, client.get("/api/anomalies", headers=USER).json()


def test_duplicate_charge(client):
    by_type, all_ = load(client,
                         gpay("2024-06-20T12:00:00", "SWIGGY", "450.00", "612400000101"),
                         gpay("2024-06-20T12:03:00", "SWIGGY", "450.00", "612400000102"),      # 3 min, other ref → duplicate
                         gpay("2024-06-21T12:00:00", "ZOMATO", "300.00", "612400000103"),
                         gpay("2024-06-21T12:15:00", "ZOMATO", "300.00", "612400000104"),      # 15 min → fine
                         r("2024-06-22", "UPI-BLINKIT-XXXX", "200.00", ref="TXN001"),
                         r("2024-06-22", "UPI-BLINKIT-XXXX", "200.00", ref="TXN002"))              # date only → can't tell
    assert [a["type"] for a in all_] == ["duplicate_charge"]
    d = by_type["duplicate_charge"]["details"]
    assert (d["merchant"], d["amount"], len(d["transactions"])) == ("Swiggy", "450.00", 2)


def test_unusual_amount(client):
    usual = [r(f"2024-05-{d:02d}", "SWIGGY", amt) for d, amt in zip((1, 3, 5, 7, 9), ("300.00", "280.00", "320.00", "300.00", "310.00"))]
    by_type, all_ = load(client, *usual, r("2024-06-10", "SWIGGY", "950.00"), r("2024-06-12", "SWIGGY", "890.00"))
    assert [a["details"]["amount"] for a in all_] == ["950.00"]        # median 300 → over 900 only
    assert by_type["unusual_amount"]["details"]["typical"] == "300.00"


def test_category_spike(client):
    rows = [r(f"2024-{m:02d}-10", "SWIGGY", "1000.00") for m in (1, 2, 3)] + [r("2024-04-10", "SWIGGY", "3000.00")]
    rows += [r("2024-04-11", "AMAZON PAY INDIA", "600.00")]           # +600 over a 0 average: under ₹1,000
    _, all_ = load(client, *rows)
    spikes = [a for a in all_ if a["type"] == "category_spike"]
    assert [(a["details"]["category"], a["details"]["amount"], a["details"]["trailing_average"], a["occurred_on"]) for a in spikes] == [
        ("Food & Dining", "3000.00", "1000.00", "2024-04-01")]


def test_unreversed_failed_upi_and_it_clears_on_reversal(client):
    by_type, _ = load(client, r("2024-06-20", "UPI/FAILED/ZEPTO", "382.00"), r("2024-06-27", "UPI PENDING BLINKIT", "199.00"))
    assert [a["details"]["amount"] for a in client.get("/api/anomalies", headers=USER).json()] == ["382.00"]   # the other is < 48 h old
    load(client, r("2024-06-22", "UPI REVERSAL ZEPTO", "382.00", "credit"))
    assert client.get("/api/anomalies", headers=USER).json() == []


def test_dismiss_via_review_persists_and_is_per_user(client):
    load(client, gpay("2024-06-20T12:00:00", "SWIGGY", "450.00", "612400000101"),
         gpay("2024-06-20T12:03:00", "SWIGGY", "450.00", "612400000102"))
    card = next(c for c in client.get("/api/review", headers=USER).json()["items"] if c["type"] == "anomaly")
    assert card["question"] == "Swiggy charged ₹450 twice within minutes. Expected?"
    assert client.get("/api/anomalies", headers=BOB).json() == []
    [a] = client.get("/api/anomalies", headers=USER).json()
    assert client.patch(f"/api/anomalies/{a['id']}", json={"status": "dismissed"}, headers=BOB).status_code == 404
    client.post(f"/api/review/{card['id']}/answer", json={"answer": "fine"}, headers=USER)
    client.post("/api/transactions/reanalyze", headers=USER)
    assert client.get("/api/anomalies", headers=USER).json() == []
    assert [x["status"] for x in client.get("/api/anomalies?status=dismissed", headers=USER).json()] == ["dismissed"]
    assert client.patch(f"/api/anomalies/{a['id']}", json={"status": "open"}, headers=USER).json()["status"] == "open"
    assert client.patch(f"/api/anomalies/{a['id']}", json={"status": "gone"}, headers=USER).status_code == 422


def test_no_spike_against_months_without_data(client):
    # Jan–Feb recorded, then nothing for Mar–May (no statements imported), then June
    rows = [r(f"2024-{m:02d}-10", "SWIGGY", "300.00") for m in (1, 2)] + [r("2024-06-10", "SWIGGY", "3000.00")]
    _, all_ = load(client, *rows)
    assert [a for a in all_ if a["type"] == "category_spike"] == []
