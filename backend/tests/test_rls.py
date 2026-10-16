"""
Row-level security (alembic a7c3e9f1d2b4). tests/test_ownership.py checks that every route filters by user; these
check the layer under it: a query that forgets the filter still gets nothing of another user's, and the API's role
can't switch the policies off.
"""

import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.crypto import CryptoError
from app.core.database import Base, SessionLocal
from app.core.scope import all_user_ids, find_user, unbind
from app.models.transaction import Budget, Transaction
from tests.conftest import as_user, owner_engine, user_session
from tests.test_end_to_end import USER, frozen_today, load_three_months  # noqa: F401 (fixture)

BOB = as_user("bob")
TABLES = [t for t in Base.metadata.sorted_tables if "user_id" in t.columns]


@pytest.fixture
def two_users(client):
    load_three_months(client)                                           # rahul: ≥ 12 tables with rows
    client.post("/api/goals", json={"name": "Bike", "target_amount": "50000", "target_date": "2024-12-01"}, headers=USER)
    client.post("/api/reports/generate", json={"period_type": "monthly", "date": "2024-05-31"}, headers=USER)
    client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "100"}, headers=BOB)
    client.post("/api/import/batch", json={"rows": [{"date": "2024-06-27", "description_raw": "SWIGGY", "amount": "900.00",
                "direction": "debit", "reference": None, "source_type": "bank_csv", "source_label": "HDFC Bank"}]}, headers=BOB)
    with owner_engine.connect() as conn:
        ids = dict(conn.execute(text("SELECT firebase_uid, id FROM users")).all())
    return ids["rahul"], ids["bob"]


def test_every_user_owned_table_has_a_policy():
    with owner_engine.connect() as conn:
        rows = dict(conn.execute(text(
            "SELECT c.relname, c.relrowsecurity AND EXISTS (SELECT FROM pg_policy p WHERE p.polrelid = c.oid) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r'")).all())
    owned = {t.name for t in TABLES} | {"users", "households"}
    assert {name for name in owned if not rows.get(name)} == set()


def test_the_api_role_cannot_bypass_policies():
    with SessionLocal() as db:
        role, superuser, bypass = db.execute(text(
            "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
        owners = {o for (o,) in db.execute(text("SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public'"))}
    assert role == "vaulta_app" and not superuser and not bypass and role not in owners
    with SessionLocal() as db, pytest.raises(ProgrammingError):
        db.execute(text("ALTER TABLE transactions DISABLE ROW LEVEL SECURITY"))


def test_a_query_without_the_user_filter_returns_only_your_rows(two_users):
    rahul, bob = two_users
    with user_session("bob") as (db, _):
        for table in TABLES:
            others = db.execute(text(f"SELECT count(*) FROM {table.name} WHERE user_id <> :u"), {"u": bob}).scalar()
            assert others == 0, table.name
        assert {t.user_id for t in db.query(Transaction)} == {bob}             # ORM, no filter at all
        assert db.execute(text("SELECT count(*) FROM transactions")).scalar() == 1
        assert [u for (u,) in db.execute(text("SELECT id FROM users"))] == [bob]
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM transactions WHERE user_id = :u"), {"u": rahul}).scalar() > 30


def test_no_bound_user_sees_nothing(two_users):
    with SessionLocal() as db:
        for table in TABLES + [Base.metadata.tables["users"]]:
            assert db.execute(text(f"SELECT count(*) FROM {table.name}")).scalar() == 0, table.name


def test_writes_for_another_user_are_refused(two_users):
    rahul, bob = two_users
    with user_session("bob") as (db, _):
        assert db.execute(text("UPDATE transactions SET category = 'x' WHERE user_id = :u"), {"u": rahul}).rowcount == 0
        assert db.execute(text("DELETE FROM budgets WHERE user_id = :u"), {"u": rahul}).rowcount == 0
        assert db.execute(text("UPDATE users SET email = 'x@x' WHERE id = :u"), {"u": rahul}).rowcount == 0
        with pytest.raises(DBAPIError, match="row-level security"):
            db.execute(text("INSERT INTO budgets (id, user_id, monthly_limit, is_active) VALUES (:i, :u, 1, true)"),
                       {"i": uuid.uuid4(), "u": rahul})
        db.rollback()
        db.add(Budget(user_id=rahul, category="Travel", monthly_limit=1))
        with pytest.raises(CryptoError):                                       # refused before it reaches the database
            db.flush()


def test_lookups_return_ids_only_and_bind_the_user(two_users):
    rahul, bob = two_users
    with SessionLocal() as db:
        assert set(all_user_ids(db)) == {rahul, bob}
        assert db.execute(text("SELECT count(*) FROM users")).scalar() == 0         # the ids, not the rows
        user = find_user(db, "firebase_uid", "rahul")
        assert user.id == rahul
        assert db.execute(text("SELECT count(*) FROM users")).scalar() == 1         # now bound to rahul
        assert find_user(db, "firebase_uid", "nobody") is None
        with pytest.raises(DBAPIError):
            db.execute(text("SELECT vaulta_find_user('email', 'x')"))
        db.rollback()
        unbind(db)


def test_the_binding_survives_commits(two_users):
    rahul, _ = two_users
    with user_session("rahul") as (db, _):
        before = db.query(Transaction).count()
        db.commit()                                                                # SET LOCAL ends with the transaction…
        assert db.query(Transaction).count() == before > 0                         # …and is applied again to the next


def test_delete_everything_still_removes_every_row(client, two_users):
    rahul, bob = two_users
    assert client.delete("/auth/me", headers=USER).status_code == 204
    with owner_engine.connect() as conn:
        tables = [t for t in inspect(owner_engine).get_table_names() if t in {x.name for x in TABLES}]
        left = {t: conn.execute(text(f"SELECT count(*) FROM {t} WHERE user_id = :u"), {"u": rahul}).scalar() for t in tables}
        assert left == {t: 0 for t in tables}
        assert conn.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": rahul}).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM transactions WHERE user_id = :u"), {"u": bob}).scalar() == 1


def test_production_refuses_a_role_that_bypasses_policies(monkeypatch):
    from app.core import database
    with owner_engine.connect() as conn:
        assert "superuser" in database.check_role(conn)
    with SessionLocal() as db:
        assert database.check_role(db.connection()) is None
    monkeypatch.setattr(database, "db_role_problem", ["bypass"])
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        next(database.get_db())
    assert e.value.status_code == 503
