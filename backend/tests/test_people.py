"""People (P2P): detection, tags, lent/borrowed balances."""

from datetime import date, timedelta

from tests.conftest import as_user
from tests.test_import_batch import row

ALICE, BOB = as_user("alice"), as_user("bob")


def days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


def p2p(d, desc, amount, direction="debit", **kw):
    return row(date=d, description_raw=desc, amount=amount, direction=direction, reference=None, **kw)


def load(client, *rows):
    if rows:
        assert client.post("/api/import/batch", json={"rows": list(rows)}, headers=ALICE).status_code == 200
    people = {p["name"]: p for p in client.get("/api/people", headers=ALICE).json()["people"]}
    txns = client.get("/api/transactions?page_size=200", headers=ALICE).json()["items"]
    return people, txns


def test_people_detected_from_bank_and_upi_apps(client):
    people, txns = load(
        client,
        p2p(days_ago(10), "UPI-RAHUL SHARMA-R***@okaxis-XXXX-Sent", "500.00"),
        p2p(days_ago(9), "UPI-RAHUL SHARMA-R***@okaxis-XXXX-Dinner", "700.00"),
        p2p(days_ago(8), "Priya Nair", "1200.00", "credit", source_type="upi_google_pay", source_label="Google Pay"),
        p2p(days_ago(7), "UPI-SWIGGY-swiggy.rzp@axisbank-XXXX", "300.00"),
    )
    assert set(people) == {"Rahul Sharma", "Priya Nair"}
    rahul = people["Rahul Sharma"]
    assert (rahul["masked_vpa"], rahul["paid_total"], rahul["transaction_count"]) == ("R***@okaxis", "1200.00", 2)
    assert people["Priya Nair"]["received_total"] == "1200.00"
    swiggy = next(t for t in txns if "SWIGGY" in t["merchant_raw"])
    assert swiggy["person_id"] is None


def test_tag_applies_to_past_and_future_unless_overridden(client):
    people, txns = load(client, *[p2p(days_ago(d), "UPI-RAHUL SHARMA-R***@okaxis-XXXX", "15000.00") for d in (60, 30)])
    first = txns[-1]
    client.patch(f"/api/transactions/{first['id']}", json={"category": "Other"}, headers=ALICE)   # individual override
    res = client.patch(f"/api/people/{people['Rahul Sharma']['id']}", json={"tag": "Rent", "display_name": "Landlord"}, headers=ALICE)
    assert res.status_code == 200, res.text
    assert (res.json()["tag"], res.json()["default_category"], res.json()["default_kind"]) == ("Rent", "Rent & Housing", "spend")

    _, txns = load(client, p2p(days_ago(0), "UPI-RAHUL SHARMA-R***@okaxis-XXXX", "15000.00"))
    by_id = {t["id"]: t for t in txns}
    assert by_id[first["id"]]["category"] == "Other"
    assert sorted(t["category"] for t in txns) == ["Other", "Rent & Housing", "Rent & Housing"]
    # list filter by person
    assert client.get(f"/api/transactions?person_id={people['Rahul Sharma']['id']}", headers=ALICE).json()["total"] == 3


def test_lent_tag_and_partial_repayment_balance(client):
    people, txns = load(client, p2p(days_ago(18), "UPI-AMIT KUMAR-A***@oksbi-XXXX", "2000.00"),
                        p2p(days_ago(5), "UPI-AMIT KUMAR-A***@oksbi-XXXX", "800.00", "credit"))
    amit = people["Amit Kumar"]
    lent = next(t for t in txns if t["direction"] == "debit")
    back = next(t for t in txns if t["direction"] == "credit")
    client.patch(f"/api/transactions/{lent['id']}", json={"kind": "lent"}, headers=ALICE)

    from app.core.database import SessionLocal
    from app.models.transaction import Transaction
    from app.services.people import repayment_candidates
    with SessionLocal() as db:
        txs = db.query(Transaction).all()
        assert [str(t.id) for t in repayment_candidates(txs)] == [back["id"]]

    client.patch(f"/api/transactions/{back['id']}", json={"kind": "repayment"}, headers=ALICE)
    people, _ = load(client)
    amit = people["Amit Kumar"]
    assert (amit["owed_to_you"], amit["balance"], amit["outstanding_days"]) == ("1200.00", "1200.00", 18)
    summary = client.get("/api/transactions/summary?period=lifetime", headers=ALICE).json()
    assert summary["total_spend"] == "0.00" and summary["total_received"] == "0.00"


def test_borrowed_balance_is_negative(client):
    people, txns = load(client, p2p(days_ago(3), "Priya Nair", "5000.00", "credit",
                                    source_type="upi_google_pay", source_label="Google Pay"))
    client.patch(f"/api/transactions/{txns[0]['id']}", json={"kind": "borrowed"}, headers=ALICE)
    people, _ = load(client)
    assert (people["Priya Nair"]["you_owe"], people["Priya Nair"]["balance"]) == ("5000.00", "-5000.00")


def test_person_validation_and_isolation(client):
    people, _ = load(client, p2p(days_ago(1), "UPI-RAHUL SHARMA-R***@okaxis-XXXX", "100.00"))
    pid = people["Rahul Sharma"]["id"]
    for bad in [{}, {"tag": "Enemy"}, {"default_category": "Bribes"}, {"default_kind": "refund"}, {"display_name": None}]:
        assert client.patch(f"/api/people/{pid}", json=bad, headers=ALICE).status_code == 422, bad
    assert client.get("/api/people", headers=BOB).json() == {"people": []}
    assert client.patch(f"/api/people/{pid}", json={"tag": "Rent"}, headers=BOB).status_code == 404
    assert load(client)[0]["Rahul Sharma"]["tag"] is None
