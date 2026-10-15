"""Budgets: soft-delete bug, partial unique index, kind-correct consumption, suggestions."""

from datetime import date

from app.services.recurring import add_months
from tests.conftest import as_user
from tests.test_import_batch import row

ALICE = as_user("alice")


def create(client, category, limit):
    return client.post("/api/budgets", json={"category": category, "monthly_limit": limit}, headers=ALICE)


def test_delete_then_recreate_reactivates_the_row(client):
    first = create(client, "Food & Dining", "5000").json()
    assert first["is_active"] is True
    assert create(client, "Food & Dining", "6000").status_code == 409
    assert client.delete(f"/api/budgets/{first['id']}", headers=ALICE).status_code == 204
    again = create(client, "Food & Dining", "7000")           # was a 500 (unique constraint covered deleted rows)
    assert again.status_code == 201
    assert (again.json()["id"], again.json()["monthly_limit"], again.json()["is_active"]) == (first["id"], "7000.00", True)
    assert [b["category"] for b in client.get("/api/budgets", headers=ALICE).json()["items"]] == ["Food & Dining"]


def test_overall_cap_is_unique_too(client):
    assert create(client, None, "40000").status_code == 201
    assert create(client, None, "50000").status_code == 409   # NULL category used to slip past the check


def test_database_enforces_one_active_budget_per_category(client):
    import pytest
    from sqlalchemy.exc import IntegrityError
    from app.core.database import SessionLocal
    from app.models.transaction import Budget
    from app.models.user import User
    create(client, "Travel", "3000")
    with SessionLocal() as db:
        user = db.query(User).filter_by(firebase_uid="alice").one()
        db.add(Budget(user_id=user.id, category="Travel", monthly_limit=1, is_active=True))
        with pytest.raises(IntegrityError):
            db.commit()


def test_suggested_budgets_in_review_queue(client):
    first = add_months(date.today().replace(day=1), -3)
    rows = []
    for i, amount in enumerate(["4200.00", "5100.00", "3900.00"]):
        month = add_months(first, i)
        rows.append(row(date=month.replace(day=10).isoformat(), description_raw="SWIGGY", amount=amount, reference=None))
    rows.append(row(date=add_months(first, 1).replace(day=12).isoformat(), description_raw="UBER", amount="800.00", reference=None))
    client.post("/api/import/batch", json={"rows": rows}, headers=ALICE)
    cards = {c["id"]: c for c in client.get("/api/review", headers=ALICE).json()["items"] if c["type"] == "budget"}
    assert set(cards) == {"budget:Food & Dining"}           # Transport's median month is ₹0
    food = cards["budget:Food & Dining"]
    assert food["question"] == "Set a ₹4,200 monthly budget for Food & Dining?"
    assert food["detail"] == "Your last 3 months: ₹4,200, ₹5,100, ₹3,900."
    assert client.post(f"/api/review/{food['id']}/answer", json={"answer": "set"}, headers=ALICE).status_code == 200
    budgets = client.get("/api/budgets", headers=ALICE).json()["items"]
    assert [(b["category"], b["monthly_limit"]) for b in budgets] == [("Food & Dining", "4200.00")]


def test_no_suggestions_without_three_full_months(client):
    client.post("/api/import/batch", json={"rows": [row(date=date.today().isoformat(), description_raw="SWIGGY",
                                                        amount="500.00", reference=None)]}, headers=ALICE)
    assert [c for c in client.get("/api/review", headers=ALICE).json()["items"] if c["type"] == "budget"] == []
