"""row-level security on every user-owned table

Each user-owned table gets a policy: a row is visible and writable only when its user_id equals the transaction's
app.user_id setting, which the API sets for each request and each unit of work (app/core/scope.py). With app.user_id
unset, no row is visible. Policies apply to the API's role (vaulta_app: not the owner, no BYPASSRLS); the owner that
runs migrations is exempt (RLS is enabled, not forced).

Before a user is known, the API finds them only through these SECURITY DEFINER functions (owned by the migration
role, so they see past RLS, and each returns ids only):
  vaulta_find_user(field, value)        → users.id by firebase_uid | inbound_token_hash | telegram_chat_id | razorpay_subscription_id
  vaulta_user_ids()                     → every user id, oldest first (the hourly run)
  vaulta_telegram_code_user(code_hash)  → the user a Telegram link code belongs to
  vaulta_release_telegram_chat(chat_id) → unlinks a Telegram chat from whoever had it (one account per chat)

Grants go to the role vaulta_app when it exists (docs/deploy.md creates it); default privileges cover later tables.

Revision ID: a7c3e9f1d2b4
Revises: f6a2c8e0b1d3
Create Date: 2026-10-16
"""
from alembic import op

revision = "a7c3e9f1d2b4"
down_revision = "f6a2c8e0b1d3"
branch_labels = None
depends_on = None

APP_ROLE = "vaulta_app"

USER_TABLES = [
    "alerts", "anomalies", "budgets", "cash_declarations", "chat_actions", "chat_messages", "corrections",
    "gmail_confirmations", "goal_entries", "goals", "import_templates", "inbound_events", "people", "recurring_series",
    "reports", "review_dismissals", "rules", "telegram_entries", "telegram_link_codes", "transaction_sources",
    "transactions",
]

FUNCTIONS = """
CREATE FUNCTION vaulta_current_user_id() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$;

CREATE FUNCTION vaulta_find_user(field text, value text) RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE found uuid;
BEGIN
  IF field = 'firebase_uid' THEN SELECT id INTO found FROM users WHERE firebase_uid = value;
  ELSIF field = 'inbound_token_hash' THEN SELECT id INTO found FROM users WHERE inbound_token_hash = value;
  ELSIF field = 'telegram_chat_id' THEN SELECT id INTO found FROM users WHERE telegram_chat_id = value::bigint;
  ELSIF field = 'razorpay_subscription_id' THEN SELECT id INTO found FROM users WHERE razorpay_subscription_id = value LIMIT 1;
  ELSE RAISE EXCEPTION 'vaulta_find_user: unknown field %', field;
  END IF;
  RETURN found;
END $$;

CREATE FUNCTION vaulta_user_ids() RETURNS SETOF uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT id FROM users ORDER BY created_at, id $$;

CREATE FUNCTION vaulta_telegram_code_user(hash text) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
$$ SELECT user_id FROM telegram_link_codes WHERE code_hash = hash $$;

CREATE FUNCTION vaulta_release_telegram_chat(chat bigint) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS
$$ UPDATE users SET telegram_chat_id = NULL WHERE telegram_chat_id = chat $$;
"""

DEFINERS = ["vaulta_find_user(text, text)", "vaulta_user_ids()", "vaulta_telegram_code_user(text)",
            "vaulta_release_telegram_chat(bigint)"]


GRANTS = """
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'APP_ROLE') THEN
    GRANT USAGE ON SCHEMA public TO APP_ROLE;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO APP_ROLE;
    REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM APP_ROLE;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO APP_ROLE;
    GRANT EXECUTE ON FUNCTION DEFINERS_LIST TO APP_ROLE;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO APP_ROLE;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO APP_ROLE;
  END IF;
END $$;"""


def upgrade() -> None:
    op.execute(FUNCTIONS)
    for fn in DEFINERS:
        # constant table/function names from this module; DDL takes no bind parameters
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
    for table in USER_TABLES:
        # constant table/function names from this module; DDL takes no bind parameters
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY user_isolation ON {table} USING (user_id = vaulta_current_user_id()) "
                   f"WITH CHECK (user_id = vaulta_current_user_id())")
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY user_isolation ON users USING (id = vaulta_current_user_id()) WITH CHECK (id = vaulta_current_user_id())")
    op.execute("ALTER TABLE households ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY user_isolation ON households USING (owner_user_id = vaulta_current_user_id()) "
               "WITH CHECK (owner_user_id = vaulta_current_user_id())")
    op.execute(GRANTS.replace("APP_ROLE", APP_ROLE).replace("DEFINERS_LIST", ", ".join(DEFINERS)))


def downgrade() -> None:
    for table in USER_TABLES + ["users", "households"]:
        # constant table/function names from this module; DDL takes no bind parameters
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        op.execute(f"DROP POLICY IF EXISTS user_isolation ON {table}")
        # constant table/function names from this module; DDL takes no bind parameters
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for fn in DEFINERS + ["vaulta_current_user_id()"]:
        # constant table/function names from this module; DDL takes no bind parameters
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
