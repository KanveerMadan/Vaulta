"""
API test harness.

Needs a disposable local Postgres (models use Postgres enums/UUIDs):
    TEST_DATABASE_URL=postgresql://user@localhost:5432/vaulta_test
Default: postgresql://vaulta@localhost:54329/vaulta_test. Refuses non-local URLs.

Auth: Firebase token verification is replaced so that the bearer token IS the
user's uid ("Authorization: Bearer alice"); the real get_current_user runs.
"""

import json
import os
from urllib.parse import urlparse

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://vaulta@localhost:54329/vaulta_test")
assert urlparse(TEST_DATABASE_URL).hostname in ("localhost", "127.0.0.1"), "tests only run against a local database"


def _fake_service_account() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return json.dumps({
        "type": "service_account", "project_id": "vaulta-test", "private_key_id": "test",
        "private_key": pem.decode(), "client_email": "test@vaulta-test.iam.gserviceaccount.com",
        "client_id": "0", "token_uri": "https://oauth2.googleapis.com/token",
    })


# Environment beats backend/.env in pydantic-settings, so nothing real is used.
os.environ.update({
    "DATABASE_URL": TEST_DATABASE_URL,
    "ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "FIREBASE_SERVICE_ACCOUNT_JSON": _fake_service_account(),
    "ENVIRONMENT": "test",
    "RAZORPAY_KEY_ID": "",
    "RAZORPAY_KEY_SECRET": "",
})

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.core.auth as auth  # noqa: E402
from app.core.database import Base, engine, wait_for_db  # noqa: E402
from app.main import app as api  # noqa: E402
from app.models import correction, import_template, transaction_source  # noqa: E402,F401 — register tables


@pytest.fixture(scope="session", autouse=True)
def schema():
    wait_for_db()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth, "verify_firebase_token", lambda token: {"uid": token, "email": f"{token}@test.local"})
    with TestClient(api) as c:
        yield c


def as_user(uid: str) -> dict:
    return {"Authorization": f"Bearer {uid}"}
