"""
Checks for the staging rehearsal (scripts/staging-rehearsal.sh). Prints counts and pass/fail lines only, never any
user's data. Run from backend/.

  python scripts/staging_verify.py before <owner_url> <state.json>
      row counts of every table, saved to state.json
  python scripts/staging_verify.py after <owner_url> <app_url> <state.json>
      after the migrations: row counts preserved, every transaction has a kind, no plaintext left in encrypted
      columns, every user has a data key, RLS on every user table, the app role sees nothing unbound and only one
      user's rows when bound, and each user's last three months of spending computed through the app's own code
Exit status 1 if any check fails.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text  # noqa: E402

ENCRYPTED = {   # table → [(column, prefix)] from alembic f6a2c8e0b1d3
    "transactions": [("merchant_raw", "e1:"), ("merchant_clean", "s1:"), ("notes", "e1:"), ("raw_source_data", "e1:")],
    "transaction_sources": [("counterparty_raw", "e1:"), ("raw_row", "e1:"), ("utr", "s1:"), ("vpa", "s1:")],
    "people": [("display_name", "e1:"), ("key_hash", "s1:")],
    "rules": [("merchant_label", "e1:"), ("merchant_key", "s1:")],
    "recurring_series": [("display_name", "e1:"), ("key", "s1:")],
    "chat_messages": [("content", "e1:")],
    "reports": [("narrative", "e1:"), ("json", "e1:")],
    "goals": [("name", "e1:")],
    "alerts": [("message", "e1:")],
}
failures = 0


def check(ok: bool, label: str) -> None:
    global failures
    print(("PASS " if ok else "FAIL ") + label)
    failures += 0 if ok else 1


def counts(engine) -> dict:
    with engine.connect() as conn:
        tables = [t for t in inspect(conn).get_table_names() if t != "alembic_version"]
        # table names come from the database's own catalogue
        return {t: conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() for t in sorted(tables)}  # nosec B608 # nosemgrep


def before(owner_url: str, state: str) -> None:
    c = counts(create_engine(owner_url))
    Path(state).write_text(json.dumps(c))
    print(f"recorded row counts of {len(c)} tables: users {c.get('users', 0)}, transactions {c.get('transactions', 0)}")


def after(owner_url: str, app_url: str, state: str) -> None:
    owner = create_engine(owner_url)
    old = json.loads(Path(state).read_text())
    new = counts(owner)
    for table, n in old.items():
        if table == "rate_limits":
            continue
        check(new.get(table) == n, f"{table}: {n} rows before, {new.get(table)} after")
    with owner.connect() as conn:
        check(conn.execute(text("SELECT count(*) FROM transactions WHERE kind IS NULL")).scalar() == 0,
              "every transaction has a kind")
        check(conn.execute(text("SELECT count(*) FROM users WHERE data_key IS NULL")).scalar() == 0, "every user has a data key")
        for table, cols in ENCRYPTED.items():
            for col, prefix in cols:
                # constant table and column names from ENCRYPTED above
                left = conn.execute(text(f'SELECT count(*) FROM {table} WHERE "{col}" IS NOT NULL '  # nosec B608 # nosemgrep
                                         f"AND \"{col}\"::text NOT LIKE '{prefix}%'")).scalar()
                check(left == 0, f"{table}.{col}: no plaintext ({left} rows not encrypted)")
        missing = conn.execute(text(
            "SELECT c.relname FROM pg_class c JOIN information_schema.columns k ON k.table_name = c.relname "
            "AND k.column_name = 'user_id' WHERE c.relkind = 'r' AND NOT c.relrowsecurity")).scalars().all()
        check(missing == [], f"row-level security on every table with user_id {missing or ''}")
        user_ids = conn.execute(text("SELECT id FROM users WHERE firebase_uid <> 'vaulta-demo' ORDER BY created_at")).scalars().all()

    app = create_engine(app_url)
    with app.connect() as conn:
        role = conn.execute(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")).scalar()
        check(role is False, "the app role can't bypass row-level security")
        check(conn.execute(text("SELECT count(*) FROM transactions")).scalar() == 0, "the app role sees no rows with no user bound")

    from app.core.database import SessionLocal  # noqa: E402 (DATABASE_URL is the app role)
    from app.core.scope import find_user, unbind  # noqa: E402
    from app.services import analytics  # noqa: E402
    from app.core import clock  # noqa: E402
    end = clock.today()
    start = (end.replace(day=1) - __import__("datetime").timedelta(days=62)).replace(day=1)
    for n, uid in enumerate(user_ids, 1):
        with SessionLocal() as db:
            user = find_user(db, "id", uid)
            visible = db.execute(text("SELECT count(DISTINCT user_id) FROM transactions")).scalar()
            check(visible in (0, 1), f"user {n}: bound session sees one account's rows")
            months = analytics.spend_summary(db, user.id, start, end, "month")
            totals = ", ".join(f"{g['key'][:7]} ₹{g['total']}" for g in months["groups"]) or "no spending"
            merchants = len(analytics.spend_summary(db, user.id, start, end, "merchant")["groups"])
            print(f"     user {n}: spend by month {totals}; {merchants} merchants decrypted and grouped")
            unbind(db)
    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{failures} CHECK(S) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    {"before": lambda a: before(*a), "after": lambda a: after(*a)}[sys.argv[1]](sys.argv[2:])
