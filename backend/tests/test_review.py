"""Review queue: one card per question, answers change the data."""

from datetime import date, timedelta

from app.services.recurring import add_months
from tests.conftest import as_user
from tests.test_import_batch import row

ALICE, BOB = as_user("alice"), as_user("bob")
TODAY = date.today()


def d(n):
    return (TODAY - timedelta(days=n)).isoformat()


def r(day, desc, amount, direction="debit", **kw):
    return row(date=day, description_raw=desc, amount=amount, direction=direction, reference=None, **kw)


def load(client, *rows):
    assert client.post("/api/import/batch", json={"rows": list(rows)}, headers=ALICE).status_code == 200


def queue(client, headers=ALICE):
    return client.get("/api/review", headers=headers).json()


def card(client, type_):
    return next(c for c in queue(client)["items"] if c["type"] == type_)


def answer(client, c, value, headers=ALICE):
    return client.post(f"/api/review/{c['id']}/answer", json={"answer": value}, headers=headers)


def txn(client, desc):
    return next(t for t in client.get("/api/transactions?page_size=200", headers=ALICE).json()["items"] if t["merchant_raw"] == desc)


def test_one_sided_transfer(client):
    load(client, r(d(3), "TRANSFER TO OWN A/C 4321", "8000.00"), r(d(2), "CC PAYMENT 9876", "3000.00"))
    c = card(client, "transfer")
    assert "a transfer between your own accounts?" in c["question"]
    assert [o["value"] for o in c["options"]] == ["transfer", "spend", "skip"]
    assert answer(client, c, "transfer").status_code == 200
    assert txn(client, "TRANSFER TO OWN A/C 4321")["kind"] == "transfer" or txn(client, "CC PAYMENT 9876")["kind"] == "transfer"
    remaining = [c for c in queue(client)["items"] if c["type"] == "transfer"]
    assert len(remaining) == 1
    answer(client, remaining[0], "spend")                       # "no" also settles it
    assert [c for c in queue(client)["items"] if c["type"] == "transfer"] == []


def test_person_paid_repeatedly(client):
    load(client, *[r(d(n), "UPI-RAHUL SHARMA-R***@okaxis-XXXX", "3000.00") for n in (70, 40, 10)])
    c = card(client, "person")
    assert c["question"] == "Paid R***@okaxis ₹3,000 three times. What is it?"
    assert [o["label"] for o in c["options"]] == ["Rent", "Split", "Lent", "Other", "Skip"]
    answer(client, c, "Rent")
    people = client.get("/api/people", headers=ALICE).json()["people"]
    assert (people[0]["tag"], people[0]["default_category"]) == ("Rent", "Rent & Housing")
    assert {t["category"] for t in client.get("/api/transactions", headers=ALICE).json()["items"]} == {"Rent & Housing"}
    assert [c for c in queue(client)["items"] if c["type"] == "person"] == []


def test_people_come_first_largest_total_first(client):
    load(client,
         *[r(d(n), "UPI-ASHA MEHTA-A***@okaxis-XXXX", "300.00") for n in (60, 30, 5)],     # ₹900 over three payments
         r(d(20), "UPI-VIKRAM RAO-V***@okhdfc-XXXX", "15000.00"),                       # one big payment: still asked
         r(d(12), "UPI-NEHA JAIN-N***@ybl-XXXX", "150.00"),                              # one small payment: not asked
         r(d(9), "TRANSFER TO OWN A/C 4321", "8000.00"))                                  # a transfer card, after people
    items = queue(client)["items"]
    kinds = [c["type"] for c in items]
    people = [c["question"] for c in items if c["type"] == "person"]
    assert kinds[:2] == ["person", "person"] and "transfer" in kinds[2:]
    assert people[0].startswith("Paid V***@okhdfc ₹15,000 once") and people[1].startswith("Paid A***@okaxis ₹300 three times")
    assert not any("N***@ybl" in q for q in people)


def test_repayment_suggestion(client):
    load(client, r(d(20), "UPI-AMIT KUMAR-A***@oksbi-XXXX", "2000.00"), r(d(4), "UPI-AMIT KUMAR-A***@oksbi-XXXX", "2000.00", "credit"))
    lent = next(t for t in client.get("/api/transactions", headers=ALICE).json()["items"] if t["direction"] == "debit")
    client.patch(f"/api/transactions/{lent['id']}", json={"kind": "lent"}, headers=ALICE)
    c = card(client, "repayment")
    assert c["question"] == "Amit Kumar sent you ₹2,000. Is it a repayment?"
    answer(client, c, "repayment")
    amit = client.get("/api/people", headers=ALICE).json()["people"][0]
    assert amit["balance"] == "0.00"


def test_recurring_confirm(client):
    load(client, *[r(add_months(TODAY, -k).isoformat(), "NETFLIX COM", "649.00") for k in (2, 1, 0)])
    c = card(client, "recurring")
    assert c["question"] == "Netflix: ₹649 every month. Track it as recurring?"
    answer(client, c, "confirmed")
    assert client.get("/api/recurring", headers=ALICE).json()["series"][0]["user_status"] == "confirmed"


def test_unknown_merchant_creates_rule(client, rules_only):
    load(client, r(d(5), "SRI SAI TIFFINS", "120.00"), r(d(3), "SRI SAI TIFFINS", "80.00"))
    c = card(client, "merchant")
    assert (c["question"], c["detail"].split(".")[0]) == ("What is “Sri Sai Tiffins”?", "₹200 across 2 payments")
    answer(client, c, "Food & Dining")
    rules = client.get("/api/rules", headers=ALICE).json()["rules"]
    assert [(r_["merchant"], r_["value"], r_["origin"]) for r_ in rules] == [("Sri Sai Tiffins", "Food & Dining", "review")]
    load(client, r(d(1), "SRI SAI TIFFINS", "60.00"))
    assert txn(client, "SRI SAI TIFFINS")["category"] == "Food & Dining"


def test_skip_is_remembered_and_answers_are_validated(client, rules_only):
    load(client, r(d(5), "SRI SAI TIFFINS", "120.00"))
    c = card(client, "merchant")
    assert answer(client, c, "Bribes").status_code == 422
    assert client.post("/api/review/merchant:0000000000000000/answer", json={"answer": "skip"}, headers=ALICE).status_code == 404
    assert client.post(f"/api/review/{c['id']}/answer", json={"answer": "skip", "x": 1}, headers=ALICE).status_code == 422
    before = queue(client)["count"]
    answer(client, c, "skip")
    assert queue(client)["count"] == before - 1


def test_review_is_per_user(client, rules_only):
    load(client, r(d(5), "SRI SAI TIFFINS", "120.00"))
    c = card(client, "merchant")
    assert queue(client, BOB) == {"count": 0, "items": []}
    assert answer(client, c, "Food & Dining", headers=BOB).status_code == 404
    assert card(client, "merchant")["id"] == c["id"]
