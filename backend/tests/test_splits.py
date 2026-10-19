"""Split transactions."""

from tests.conftest import as_user
from tests.test_import_batch import row

ALICE, BOB = as_user("alice"), as_user("bob")
MARCH = "/api/transactions/summary?period=month&year=2024&month=3"


def setup(client):
    client.post("/api/import/batch", json={"rows": [row(description_raw="DMART AVENUE", amount="3000.00", reference=None)]}, headers=ALICE)
    return client.get("/api/transactions", headers=ALICE).json()["items"][0]


def split(client, txn, parts, headers=ALICE):
    return client.post(f"/api/transactions/{txn['id']}/split", json={"parts": parts}, headers=headers)


def categories(client):
    return {c["category"]: c["total"] for c in client.get(MARCH, headers=ALICE).json()["categories"]}


def test_split_counts_parts_instead_of_parent_and_unsplit_restores(client):
    txn = setup(client)
    assert categories(client) == {"Groceries": "3000.00"}
    res = split(client, txn, [{"amount": "2000", "category": "Groceries"}, {"amount": "1000.00", "category": "Shopping"}])
    assert res.status_code == 200, res.text
    assert res.json()["is_split"] is True
    assert [(p["amount"], p["category"]) for p in res.json()["splits"]] == [("2000.00", "Groceries"), ("1000.00", "Shopping")]
    assert categories(client) == {"Groceries": "2000.00", "Shopping": "1000.00"}
    summary = client.get(MARCH, headers=ALICE).json()
    assert (summary["total_spend"], summary["transaction_count"]) == ("3000.00", 2)
    listed = client.get("/api/transactions", headers=ALICE).json()
    assert listed["total"] == 1 and len(listed["items"][0]["splits"]) == 2

    # a part's category can be changed; detection leaves it alone
    part = listed["items"][0]["splits"][1]
    client.patch(f"/api/transactions/{part['id']}", json={"category": "Health"}, headers=ALICE)
    client.post("/api/transactions/reanalyze", headers=ALICE)
    assert categories(client) == {"Groceries": "2000.00", "Health": "1000.00"}

    assert client.delete(f"/api/transactions/{txn['id']}/split", headers=ALICE).json()["splits"] == []
    assert categories(client) == {"Groceries": "3000.00"}


def test_split_validation(client):
    txn = setup(client)
    assert split(client, txn, [{"amount": "2000", "category": "Groceries"}, {"amount": "999", "category": "Shopping"}]).status_code == 422
    assert split(client, txn, [{"amount": "3000", "category": "Groceries"}]).status_code == 422
    assert split(client, txn, [{"amount": "3000", "category": "Groceries"}, {"amount": "0", "category": None}]).status_code == 422
    assert split(client, txn, [{"amount": "1500", "category": "Bribes"}, {"amount": "1500"}]).status_code == 422
    assert client.delete(f"/api/transactions/{txn['id']}/split", headers=ALICE).status_code == 422
    ok = split(client, txn, [{"amount": "1500", "category": "Groceries"}, {"amount": "1500"}]).json()
    assert split(client, txn, [{"amount": "1500"}, {"amount": "1500"}]).status_code == 422          # already split
    part = ok["splits"][0]
    assert client.post(f"/api/transactions/{part['id']}/split", json={"parts": [{"amount": "750"}, {"amount": "750"}]},
                       headers=ALICE).status_code == 422                                              # parts can't split


def test_split_is_per_user(client):
    txn = setup(client)
    assert split(client, txn, [{"amount": "1500"}, {"amount": "1500"}], headers=BOB).status_code == 404
    split(client, txn, [{"amount": "1500"}, {"amount": "1500"}])
    assert client.delete(f"/api/transactions/{txn['id']}/split", headers=BOB).status_code == 404
    assert client.get("/api/transactions", headers=ALICE).json()["items"][0]["is_split"] is True
