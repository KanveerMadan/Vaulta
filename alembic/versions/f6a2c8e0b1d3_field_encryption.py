"""field-level encryption: per-user data keys, encrypted columns

Upgrade: adds users.data_key, widens the encrypted columns to text, gives every user a data key (wrapped by
MASTER_KEY) and encrypts every value in place (app/core/crypto.py), in batches of BATCH rows. Values that already
decrypt with their user's key are skipped, so re-running after an interruption is safe (and the whole migration is
one transaction, so an interrupted run leaves nothing half-written).
Phase 4 forwarding tokens (Fernet, ENCRYPTION_KEY) are moved to the user's key and their lookup hash becomes an HMAC.

Downgrade: decrypts every value back to plaintext and restores the previous column types. Forwarding tokens go back
to Fernet when ENCRYPTION_KEY is set; otherwise they are cleared (the user gets a new address).

Needs MASTER_KEY and BLIND_INDEX_KEY in the environment (the same values the API uses).

Revision ID: f6a2c8e0b1d3
Revises: a5c1e7f9b0d3
Create Date: 2026-10-16
"""
import hashlib
import uuid

import sqlalchemy as sa
from alembic import op

revision = "f6a2c8e0b1d3"
down_revision = "a5c1e7f9b0d3"
branch_labels = None
depends_on = None

BATCH = 500

# table → [(column, previous type, searchable)]
COLUMNS = {
    "transactions": [("merchant_raw", "varchar", False), ("merchant_clean", "varchar", True),
                     ("notes", "varchar(500)", False), ("raw_source_data", "json", False)],
    "transaction_sources": [("utr", "varchar", True), ("vpa", "varchar", True),
                            ("counterparty_raw", "varchar", False), ("raw_row", "json", False)],
    "people": [("key_hash", "varchar(64)", True), ("display_name", "varchar(100)", False),
               ("masked_vpa", "varchar(80)", False)],
    "recurring_series": [("key", "varchar(100)", True), ("display_name", "varchar(100)", False),
                         ("user_name", "varchar(100)", False)],
    "rules": [("merchant_key", "varchar(100)", True), ("merchant_label", "varchar(100)", False)],
    "goals": [("name", "varchar(80)", False)],
    "chat_messages": [("content", "text", False)],
    "chat_actions": [("args", "json", False), ("summary", "varchar(300)", False)],
    "reports": [("json", "json", False), ("narrative", "text", False)],
    "anomalies": [("key", "varchar(160)", True), ("details", "json", False)],
    "alerts": [("key", "varchar(200)", True), ("message", "varchar(500)", False)],
    "review_dismissals": [("card_id", "varchar(120)", True)],
    "telegram_entries": [("payload", "json", False)],
}


def _crypto():
    from app.core import crypto
    return crypto


def _ciphers(conn, create: bool) -> dict:
    """user id → UserCipher, creating missing data keys on upgrade."""
    crypto = _crypto()
    out = {}
    for uid, wrapped in conn.execute(sa.text("SELECT id, data_key FROM users")).all():
        if not wrapped:
            if not create:
                continue
            wrapped = crypto.wrap(crypto.new_data_key(), uid)
            conn.execute(sa.text("UPDATE users SET data_key = :k WHERE id = :u"), {"k": wrapped, "u": uid})
        out[uid] = crypto.UserCipher(uid, crypto.unwrap(wrapped, uid))
    return out


def _decrypted(cipher, value):
    """The plaintext if `value` is one of this user's ciphertexts, else None."""
    crypto = _crypto()
    if not crypto.is_encrypted(value):
        return None
    try:
        return cipher.decrypt(value)
    except crypto.CryptoError:
        return None


def _rewrite(conn, ciphers: dict, encrypt: bool) -> None:
    for table, columns in COLUMNS.items():
        names = [c for c, _, _ in columns]
        # Table and column names come from COLUMNS above, never from data; values are bound parameters.
        # constant table/column names from COLUMNS; values are bound parameters
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        select = sa.text(f"SELECT id, user_id, {', '.join(names)} FROM {table} WHERE id > :last ORDER BY id LIMIT {BATCH}")  # nosec B608
        last = uuid.UUID(int=0)
        while True:
            rows = conn.execute(select, {"last": last}).all()
            if not rows:
                break
            for row in rows:
                last = row[0]
                cipher = ciphers.get(row[1])
                if cipher is None:
                    continue
                changes = {}
                for (name, _, searchable), value in zip(columns, row[2:]):
                    if value is None:
                        continue
                    plain = _decrypted(cipher, value)
                    if encrypt and plain is None:
                        changes[name] = cipher.encrypt(value, searchable)
                    elif not encrypt and plain is not None:
                        changes[name] = plain
                if changes:
                    sets = ", ".join(f"{n} = :{n}" for n in changes)
                    # constant table/column names from COLUMNS; values are bound parameters
                    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    conn.execute(sa.text(f"UPDATE {table} SET {sets} WHERE id = :id"), {**changes, "id": row[0]})  # nosec B608


def _fernet():
    from app.core.config import settings
    if not settings.ENCRYPTION_KEY:
        return None
    from cryptography.fernet import Fernet
    return Fernet(settings.ENCRYPTION_KEY.encode())


def _tokens_up(conn, ciphers: dict) -> None:
    crypto = _crypto()
    rows = conn.execute(sa.text("SELECT id, inbound_token_encrypted FROM users WHERE inbound_token_encrypted IS NOT NULL")).all()
    pending = [(uid, v) for uid, v in rows if _decrypted(ciphers[uid], v) is None]
    if not pending:
        return
    fernet = _fernet()
    if fernet is None:
        raise RuntimeError(f"{len(pending)} forwarding token(s) are encrypted with ENCRYPTION_KEY: set it for this migration.")
    for uid, value in pending:
        token = fernet.decrypt(value.encode()).decode()
        conn.execute(sa.text("UPDATE users SET inbound_token_encrypted = :e, inbound_token_hash = :h WHERE id = :u"),
                     {"e": ciphers[uid].encrypt(token), "h": crypto.lookup_hash("inbound", token.lower()), "u": uid})


def _tokens_down(conn, ciphers: dict) -> None:
    fernet = _fernet()
    rows = conn.execute(sa.text("SELECT id, inbound_token_encrypted FROM users WHERE inbound_token_encrypted IS NOT NULL")).all()
    for uid, value in rows:
        token = _decrypted(ciphers[uid], value) if uid in ciphers else None
        if token is None:
            continue
        if fernet is None:
            conn.execute(sa.text("UPDATE users SET inbound_token_encrypted = NULL, inbound_token_hash = NULL WHERE id = :u"), {"u": uid})
        else:
            conn.execute(sa.text("UPDATE users SET inbound_token_encrypted = :e, inbound_token_hash = :h WHERE id = :u"),
                         {"e": fernet.encrypt(token.encode()).decode(), "h": hashlib.sha256(token.lower().encode()).hexdigest(), "u": uid})


def upgrade() -> None:
    op.add_column("users", sa.Column("data_key", sa.Text(), nullable=True))
    for table, columns in COLUMNS.items():
        for name, _, _ in columns:
            # constant table/column names from COLUMNS; values are bound parameters
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            op.execute(f'ALTER TABLE {table} ALTER COLUMN "{name}" TYPE text USING "{name}"::text')
    op.execute("ALTER TABLE users ALTER COLUMN inbound_token_encrypted TYPE text")
    conn = op.get_bind()
    ciphers = _ciphers(conn, create=True)
    _rewrite(conn, ciphers, encrypt=True)
    _tokens_up(conn, ciphers)


def downgrade() -> None:
    conn = op.get_bind()
    ciphers = _ciphers(conn, create=False)
    _rewrite(conn, ciphers, encrypt=False)
    _tokens_down(conn, ciphers)
    for table, columns in COLUMNS.items():
        for name, previous, _ in columns:
            # constant table/column names from COLUMNS; values are bound parameters
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            op.execute(f'ALTER TABLE {table} ALTER COLUMN "{name}" TYPE {previous} USING "{name}"::{previous}')
    op.execute("ALTER TABLE users ALTER COLUMN inbound_token_encrypted TYPE varchar")
    op.drop_column("users", "data_key")
