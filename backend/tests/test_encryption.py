"""
Field-level encryption (app/core/crypto.py, alembic f6a2c8e0b1d3).

test_dump_has_no_plaintext is the guarantee /security makes: after a realistic account's worth of activity, a dump
of every table contains none of its merchant names, narrations, people, notes, goal names or chat text.
"""

import importlib.util
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg2
import pytest
from sqlalchemy import JSON, Enum, String, Text, create_engine, text

from app.core import crypto
from app.core.database import Base
from app.core.scope import bind_user, current_cipher, unbind
from app.models.user import User
from tests.conftest import TEST_DATABASE_URL, owner_engine, user_session
from tests.test_chat import call, fake, say  # noqa: F401 (fixture)
from tests.test_end_to_end import USER, frozen_today, load_three_months  # noqa: F401 (fixture)
from tests.test_migrations import alembic

REPO = Path(__file__).resolve().parents[2]

# Text from the fixture that must only ever exist encrypted (case-sensitive: these are the forms that get stored)
SECRETS = [
    "ACME CORP PAYROLL", "RAVI KUMAR", "Ravi Kumar", "R***@okaxis", "ZEPTO", "Zepto", "BESCOM", "ANKIT JAIN", "Ankit Jain",
    "NETFLIX", "Netflix", "SWIGGY", "Swiggy", "AMAZON PAY", "Amazon", "ZOMATO", "Zomato", "PRIYA", "Priya",
    "Bike trip to Ladakh", "birthday gift for Meera", "how much on biryani", "Biryani budget looks fine",
]

# Text columns on user-owned tables that stay readable, and why. Anything else must be encrypted.
PLAINTEXT_OK = {
    "users": {"firebase_uid", "email", "full_name", "timezone", "subscription_status", "razorpay_subscription_id",
              "inbound_token_hash", "data_key", "alert_prefs", "onboarding"},       # sign-in, email, settings, key material
    "transactions": {"category", "auto_category", "currency", "idempotency_key", "user_corrected", "cash_flow",
                     "subcategory", "auto_subcategory"},                              # taxonomy ids / custom:<uuid>
    "transaction_sources": {"source_label", "idempotency_key"},                      # account label ("HDFC Bank")
    "people": {"tag", "default_category", "default_kind"},
    "recurring_series": {"cadence", "status", "type_guess", "category", "user_status", "user_type", "usage"},
    "rules": {"field", "value", "origin"},                                           # category / kind names
    "goals": {"category"},
    "chat_messages": {"role"}, "chat_actions": {"token_hash", "tool", "outcome"},
    "reports": {"period_type", "narrative_source"},
    "anomalies": {"type", "status"}, "alerts": {"type", "telegram_status"},
    "budgets": {"category", "subcategory"}, "custom_subcategories": {"group"},
    "recategorisation_runs": {"summary"},                                           # category names and counts only
    "model_metrics": {"source"},                                   # no user at all: daily counts per categoriser step
    "corrections": {"field", "old_value", "new_value"},   # kind / category names only
    "import_templates": {"fingerprint", "source_type", "mapping"},                   # column indices, no header text
    "inbound_events": {"bank_key", "bank_name", "outcome"},
    "gmail_confirmations": {"link", "code"},                                         # Gmail's confirmation link
    "cash_declarations": {"reason"}, "telegram_link_codes": {"code_hash"}, "telegram_entries": {"status"},
    "review_dismissals": set(), "goal_entries": set(),
    "activity_log": {"kind", "detail"},                                              # event names, field names only
    "rate_limits": {"bucket"},                                                       # keyed hash
    "pending_auth_deletions": {"firebase_uid", "email", "last_error"},   # a deleted account's login until it goes; error type only
}


def test_every_text_column_is_encrypted_or_justified():
    for table in Base.metadata.sorted_tables:
        if table.name == "households":   # unused stub (name only, no user data)
            continue
        for col in table.columns:
            if isinstance(col.type, (crypto.Encrypted, Enum)) or not isinstance(col.type, (String, Text, JSON)):
                continue
            assert col.name in PLAINTEXT_OK.get(table.name, set()), f"{table.name}.{col.name} is stored in plaintext"


def _dump() -> str:
    with owner_engine.connect() as conn:
        return "\n".join(str(r[0]) for t in Base.metadata.sorted_tables
                         for r in conn.execute(text(f"SELECT row_to_json(t)::text FROM {t.name} t")))


def test_dump_has_no_plaintext(client, fake):
    load_three_months(client)
    goal = client.post("/api/goals", json={"name": "Bike trip to Ladakh", "target_amount": "50000", "target_date": "2024-12-01"},
                       headers=USER).json()
    client.post(f"/api/goals/{goal['id']}/entries", json={"amount": "500"}, headers=USER)
    txn = client.get("/api/transactions", headers=USER).json()["items"][0]
    client.patch(f"/api/transactions/{txn['id']}", json={"notes": "birthday gift for Meera"}, headers=USER)
    client.post("/api/reports/generate", json={"period_type": "monthly", "date": "2024-05-31"}, headers=USER)
    client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "100"}, headers=USER)
    fake(call("spend_summary", start="2024-06-01", end="2024-06-30", group_by="merchant"), say("Biryani budget looks fine."))
    assert client.post("/api/chat", json={"message": "how much on biryani last week?"}, headers=USER).status_code == 200

    # The app still reads everything back
    people = {p["name"] for p in client.get("/api/people", headers=USER).json()["people"]}
    assert "Ravi Kumar" in people
    assert client.get("/api/goals", headers=USER).json()["items"][0]["name"] == "Bike trip to Ladakh"
    assert any(t["notes"] == "birthday gift for Meera" for t in client.get("/api/transactions", headers=USER).json()["items"])

    dump = _dump()
    assert len(dump) > 50_000                                     # the dump really holds the account
    found = [s for s in SECRETS if s in dump]
    assert found == [], f"plaintext in the database: {found}"


def test_ciphertext_is_bound_to_its_user():
    with user_session_pair() as (alice, bob):
        bind_user(alice[0], alice[1])
        token = current_cipher().encrypt("Swiggy")
        searchable = current_cipher().encrypt("Swiggy", searchable=True)
        assert current_cipher().decrypt(token) == "Swiggy"
        assert current_cipher().encrypt("Swiggy") != token                       # random nonce
        assert current_cipher().encrypt("Swiggy", searchable=True) == searchable  # blind-index nonce
        bind_user(bob[0], bob[1])
        assert current_cipher().encrypt("Swiggy", searchable=True) != searchable  # per user
        with pytest.raises(crypto.CryptoError):
            current_cipher().decrypt(token)                                       # another user's key
        tampered = token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1]
        bind_user(alice[0], alice[1])
        with pytest.raises(crypto.CryptoError):
            current_cipher().decrypt(tampered)
        unbind()
        with pytest.raises(crypto.CryptoError):
            current_cipher()


class user_session_pair:
    """Two users created directly (no API), each with a session."""

    def __enter__(self):
        from app.core.database import SessionLocal
        self.sessions = []
        out = []
        for uid in ("alice", "bob"):
            db = SessionLocal()
            user = User(firebase_uid=uid, email=f"{uid}@test.local")
            bind_user(db, user)
            db.add(user)
            db.commit()
            self.sessions.append(db)
            out.append((db, user))
        return out

    def __exit__(self, *exc):
        unbind()
        for db in self.sessions:
            db.close()


def test_wrapped_key_needs_the_master_key(monkeypatch):
    uid = uuid.uuid4()
    key = crypto.new_data_key()
    wrapped = crypto.wrap(key, uid)
    assert crypto.unwrap(wrapped, uid) == key
    with pytest.raises(crypto.CryptoError):
        crypto.unwrap(wrapped, uuid.uuid4())                                      # bound to the user id
    monkeypatch.setattr(crypto.settings, "MASTER_KEY", "another-master-key-" + "x" * 32)
    with pytest.raises(crypto.CryptoError):
        crypto.unwrap(wrapped, uid)


# ── The migration, on real rows ───────────────────────────────────────────────

@pytest.fixture
def plaintext_db():
    """A fresh database at the revision before encryption, with plaintext rows for two users."""
    parsed = urlparse(TEST_DATABASE_URL)
    name = "vaulta_encryption_check"
    admin = psycopg2.connect(urlunparse(parsed._replace(path="/postgres")))
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        cur.execute(f"CREATE DATABASE {name}")
    url = urlunparse(parsed._replace(path=f"/{name}"))
    result = alembic(url, "upgrade", "a5c1e7f9b0d3")
    assert result.returncode == 0, result.stderr[-3000:]
    eng = create_engine(url)
    with eng.begin() as conn:
        for i, uid in enumerate((uuid.uuid4(), uuid.uuid4())):
            conn.execute(text("INSERT INTO users (id, firebase_uid, email, gmail_connected, sms_connected, aa_connected) "
                              "VALUES (:u, :f, :e, false, false, false)"), {"u": uid, "f": f"u{i}", "e": f"u{i}@test.local"})
            for j in range(3):
                conn.execute(text(
                    "INSERT INTO transactions (id, user_id, source, merchant_raw, merchant_clean, notes, raw_source_data, direction, "
                    "kind, amount, currency, transaction_date, idempotency_key, is_split, transaction_nature) VALUES "
                    "(:id, :u, 'csv', :raw, 'Swiggy', :note, CAST(:rawrow AS json), 'debit', 'spend', 100, 'INR', now(), :k, false, 'expense')"),
                    {"id": uuid.uuid4(), "u": uid, "raw": f"SWIGGY ORDER {j}", "note": "birthday gift for Meera" if j == 0 else None,
                     "rawrow": '{"description_raw": "SWIGGY ORDER", "reference": "412300000001"}', "k": f"{i}-{j}"})
            conn.execute(text("INSERT INTO people (id, user_id, key_hash, display_name, masked_vpa) VALUES (:id, :u, :h, 'Ravi Kumar', 'R***@okaxis')"),
                         {"id": uuid.uuid4(), "u": uid, "h": "a" * 64})
            conn.execute(text("INSERT INTO rules (id, user_id, merchant_key, merchant_label, field, value, origin) "
                              "VALUES (:id, :u, 'swiggy', 'Swiggy', 'category', 'Food & Dining', 'manual')"), {"id": uuid.uuid4(), "u": uid})
    yield url, eng
    eng.dispose()
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
    admin.close()


def _snapshot(eng) -> dict:
    with eng.connect() as conn:
        return {t: sorted(str(r) for r in conn.execute(text(f"SELECT * FROM {t} ORDER BY id")))
                for t in ("transactions", "people", "rules")}


def _migration():
    path = next((REPO / "alembic" / "versions").glob("f6a2c8e0b1d3_*.py"))
    spec = importlib.util.spec_from_file_location("field_encryption", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_encrypts_reverses_and_is_idempotent(plaintext_db):
    url, eng = plaintext_db
    before = _snapshot(eng)
    assert alembic(url, "upgrade", "f6a2c8e0b1d3").returncode == 0

    with eng.connect() as conn:
        rows = conn.execute(text("SELECT user_id, merchant_raw, merchant_clean, notes, raw_source_data FROM transactions")).all()
        keys = dict(conn.execute(text("SELECT id, data_key FROM users")).all())
        dump = "\n".join(str(r[0]) for t in ("transactions", "people", "rules")
                         for r in conn.execute(text(f"SELECT row_to_json(t)::text FROM {t} t")))
    assert not any(s in dump for s in ("SWIGGY", "Swiggy", "swiggy", "Ravi Kumar", "okaxis", "Meera", "412300000001"))
    ciphers = {uid: crypto.UserCipher(uid, crypto.unwrap(k, uid)) for uid, k in keys.items()}
    assert {ciphers[u].decrypt(c) for u, _, c, _, _ in rows} == {"Swiggy"}
    assert sorted(ciphers[u].decrypt(r) for u, r, _, _, _ in rows) == sorted([f"SWIGGY ORDER {j}" for j in range(3)] * 2)
    assert len({c for _, _, c, _, _ in rows}) == 2                     # merchant_clean: one ciphertext per user

    # Running the data pass again changes nothing
    m = _migration()
    with eng.begin() as conn:
        updates = []
        conn.connection.cursor()  # noqa: B018 (open the DBAPI connection)
        original = conn.execute

        def spy(stmt, *a, **kw):
            if str(stmt).lstrip().upper().startswith("UPDATE"):
                updates.append(str(stmt))
            return original(stmt, *a, **kw)
        conn.execute = spy
        m._rewrite(conn, m._ciphers(conn, create=False), encrypt=True)
    assert updates == []

    assert alembic(url, "downgrade", "a5c1e7f9b0d3").returncode == 0
    assert _snapshot(eng) == before                                    # every value back, byte for byte
    assert alembic(url, "upgrade", "head").returncode == 0


def test_master_key_rotation_rewraps_keys_only(client, monkeypatch):
    import importlib
    rotation = importlib.import_module("scripts.rotate_master_key")
    client.post("/api/import/batch", json={"rows": [{"date": "2024-06-27", "description_raw": "SWIGGY ORDER", "amount": "900.00",
                "direction": "debit", "reference": None, "source_type": "bank_csv", "source_label": "HDFC Bank"}]}, headers=USER)
    fields_before = _dump_table("transactions")
    old = crypto.settings.MASTER_KEY
    monkeypatch.setattr(crypto.settings, "MASTER_KEY", "rotated-master-key-" + "y" * 40)
    monkeypatch.setattr(crypto.settings, "MASTER_KEY_PREVIOUS", old)
    assert rotation.rotate(owner_engine, dry_run=True) == {"rewrapped": 1, "already_current": 0}
    assert rotation.rotate(owner_engine) == {"rewrapped": 1, "already_current": 0}
    assert rotation.rotate(owner_engine) == {"rewrapped": 0, "already_current": 1}     # re-running is a no-op
    assert _dump_table("transactions") == fields_before                                  # no field re-encrypted
    monkeypatch.setattr(crypto.settings, "MASTER_KEY_PREVIOUS", "")
    txns = client.get("/api/transactions", headers=USER).json()["items"]                 # readable with the new key alone
    assert txns[0]["merchant_raw"] == "SWIGGY ORDER"


def _dump_table(name: str) -> list:
    with owner_engine.connect() as conn:
        return sorted(str(r) for r in conn.execute(text(f"SELECT * FROM {name}")))
