"""DELETE /auth/me removes every row belonging to the user, in every table."""

from sqlalchemy import inspect, text

from tests.conftest import owner_engine, user_session
from app.core.database import Base
from app.models.user import User
from tests.test_end_to_end import USER, frozen_today, load_three_months  # noqa: F401 (fixture)


def test_delete_everything(client):
    load_three_months(client)
    goal = client.post("/api/goals", json={"name": "Bike", "target_amount": "50000", "target_date": "2024-12-01"}, headers=USER).json()
    client.post(f"/api/goals/{goal['id']}/entries", json={"amount": "500"}, headers=USER)
    client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "100"}, headers=USER)
    client.post("/api/reports/generate", json={"period_type": "monthly", "date": "2024-05-31"}, headers=USER)
    client.post("/api/cash/declare", json={"amount": "100"}, headers=USER)
    client.post("/api/telegram/link-code", headers=USER)
    client.patch("/api/onboarding", json={"banks": ["hdfc"]}, headers=USER)
    client.post("/api/import/batch", json={"rows": [{"date": "2024-06-27", "description_raw": "SWIGGY", "amount": "900.00",
                 "direction": "debit", "reference": None, "source_type": "bank_csv", "source_label": "HDFC Bank"}]}, headers=USER)
    with user_session("rahul") as (db, _user):
        uid = _user.id
    tables = [t.name for t in Base.metadata.sorted_tables if "user_id" in {c["name"] for c in inspect(owner_engine).get_columns(t.name)}]
    with owner_engine.connect() as conn:
        before = {t: conn.execute(text(f"SELECT count(*) FROM {t} WHERE user_id = :u"), {"u": uid}).scalar() for t in tables}
    assert sum(1 for n in before.values() if n) >= 12, before          # the fixture really touched most tables
    assert client.delete("/auth/me", headers=USER).status_code == 204
    with owner_engine.connect() as conn:
        after = {t: conn.execute(text(f"SELECT count(*) FROM {t} WHERE user_id = :u"), {"u": uid}).scalar() for t in tables}
        assert conn.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": uid}).scalar() == 0
    assert after == {t: 0 for t in tables}
