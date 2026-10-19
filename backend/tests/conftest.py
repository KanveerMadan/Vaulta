"""
API test harness.

Needs a disposable local Postgres (models use Postgres enums/UUIDs):
    TEST_DATABASE_URL=postgresql://user@localhost:5432/vaulta_test
Default: postgresql://vaulta@localhost:54329/vaulta_test. Refuses non-local URLs.

The schema is built by the real migrations (alembic upgrade head) as that URL's user, the tables' owner. The API
connects as vaulta_app, a role without superuser or BYPASSRLS created here if missing, exactly as in production
(docs/deploy.md), so row-level security applies to every test.

Auth: Firebase token verification is replaced so that the bearer token IS the
user's uid ("Authorization: Bearer alice"); the real get_current_user runs.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
import secrets
import time
from contextlib import contextmanager

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://vaulta@localhost:54329/vaulta_test")
assert urlparse(TEST_DATABASE_URL).hostname in ("localhost", "127.0.0.1"), "tests only run against a local database"
APP_DATABASE_URL = urlunparse(urlparse(TEST_DATABASE_URL)._replace(netloc=f"vaulta_app@{urlparse(TEST_DATABASE_URL).netloc.split('@')[-1]}"))


def _fake_service_account() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return json.dumps({
        "type": "service_account", "project_id": "vaulta-test", "private_key_id": "test",
        "private_key": pem.decode(), "client_email": "test@vaulta-test.iam.gserviceaccount.com",
        "client_id": "0", "token_uri": "https://oauth2.googleapis.com/token",
    })


# Environment beats backend/.env in pydantic-settings, so nothing real is used. This module is imported twice
# (as conftest and as tests.conftest): random keys are set once, so subprocesses (alembic) get the same ones.
for _name in ("MASTER_KEY", "BLIND_INDEX_KEY"):
    os.environ.setdefault(_name, secrets.token_urlsafe(48))
os.environ.update({
    "DATABASE_URL": APP_DATABASE_URL,
    "MIGRATION_DATABASE_URL": TEST_DATABASE_URL,
    "FIREBASE_SERVICE_ACCOUNT_JSON": _fake_service_account(),
    "ENVIRONMENT": "test",
    "BACKEND_CORS_ORIGIN_REGEX": r"^https://vaulta-[a-z0-9-]+-preview\.example$",
    "RAZORPAY_KEY_ID": "",
    "RAZORPAY_KEY_SECRET": "",
    # real third-party keys in backend/.env are never used (or printed) by tests
    **{k: "" for k in ("GROQ_API_KEY", "RESEND_API_KEY", "SENTRY_DSN", "TELEGRAM_BOT_TOKEN", "RECAPTCHA_SECRET_KEY",
                       "RAZORPAY_WEBHOOK_SECRET")},
})

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

import app.core.auth as auth  # noqa: E402
from app.core.database import Base, engine, wait_for_db  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.scope import find_user, unbind  # noqa: E402
from app.main import app as api  # noqa: E402
from app.models import activity, deletion, ratelimit, alert, anomaly, cash, chat, correction, goal, inbound, import_template, person, recurring, report, review, rule, telegram, transaction_source  # noqa: E402,F401 — register tables


# The tables' owner, for setup and for looking at raw rows (the API's engine is app.core.database.engine)
owner_engine = create_engine(TEST_DATABASE_URL)


@pytest.fixture(scope="session", autouse=True)
def schema():
    with owner_engine.begin() as conn:
        conn.execute(text("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaulta_app') THEN "
                          "CREATE ROLE vaulta_app LOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"))
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    migrate = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=Path(__file__).resolve().parents[2],
                             env=os.environ, capture_output=True, text=True)
    assert migrate.returncode == 0, migrate.stderr[-3000:]
    wait_for_db()
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    unbind()
    yield
    unbind()
    with owner_engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def client(monkeypatch):
    signed_in = int(time.time())       # one sign-in per test: a request in a later second isn't a new sign-in
    monkeypatch.setattr(auth, "verify_firebase_token",
                        lambda token, check_revoked=False: token_payload(token, auth_time=signed_in, iat=signed_in))
    with TestClient(api) as c:
        yield c


def token_payload(uid: str, **overrides) -> dict:
    """What Firebase's verify_id_token returns for a fresh, verified email/password sign-in as `uid`."""
    now = int(time.time())
    return {"uid": uid, "email": f"{uid}@test.local", "email_verified": True, "auth_time": now, "iat": now,
            "firebase": {"sign_in_provider": "password"}, **overrides}


def as_user(uid: str) -> dict:
    return {"Authorization": f"Bearer {uid}"}


@contextmanager
def user_session(uid: str):
    """A database session bound to the user signed up as `uid` (as the API binds it), yielding (db, user)."""
    with SessionLocal() as db:
        user = find_user(db, "firebase_uid", uid)
        assert user is not None, f"no user {uid}"
        try:
            yield db, user
        finally:
            unbind(db)


def reset_rate_limits() -> None:
    """Forget every rate-limit counter (they live in Postgres, shared like in production)."""
    with owner_engine.begin() as conn:
        conn.execute(text("DELETE FROM rate_limits"))


@pytest.fixture(autouse=True)
def firebase_deletions(monkeypatch):
    """Firebase Admin delete_user, faked for every test (never a network call): the uids deleted, in order."""
    from firebase_admin import auth as firebase_auth
    deleted = []
    monkeypatch.setattr(firebase_auth, "delete_user", lambda uid: deleted.append(uid))
    return deleted


@pytest.fixture
def rules_only(monkeypatch):
    """The rule-based categories alone (MERCHANT_MODEL_ENABLED=false): for tests of flows about unknown merchants."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "MERCHANT_MODEL_ENABLED", False)
