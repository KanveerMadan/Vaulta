"""Production refuses to start without real secrets."""

import secrets

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {"DATABASE_URL": "postgresql://x@localhost/x", "FIREBASE_SERVICE_ACCOUNT_JSON": "{}", "ENCRYPTION_KEY": "k"}
GOOD = secrets.token_urlsafe(48)


def make(**overrides):
    return Settings(_env_file=None, **{**BASE, **overrides})


@pytest.mark.parametrize("secret_key, internal", [
    ("change-this-to-something-long-and-random", GOOD),     # the shipped default
    (GOOD, ""),                                              # internal secret missing
    ("changeme", GOOD),
    (GOOD, "secret"),
    (GOOD, "short-but-not-a-placeholder"),                   # under 32 characters
    ("  CHANGEME  ", GOOD),
])
def test_production_refuses_weak_secrets(secret_key, internal):
    with pytest.raises(ValidationError, match="production"):
        make(ENVIRONMENT="production", SECRET_KEY=secret_key, INTERNAL_SECRET=internal)


def test_production_starts_with_real_secrets():
    s = make(ENVIRONMENT="production", SECRET_KEY=GOOD, INTERNAL_SECRET=secrets.token_urlsafe(48))
    assert s.ENVIRONMENT == "production"


def test_development_allows_defaults():
    assert make(ENVIRONMENT="development").SECRET_KEY == "change-this-to-something-long-and-random"


def test_app_exits_at_startup_in_production_without_secrets(tmp_path):
    import os
    import subprocess
    import sys
    env = {**os.environ, "ENVIRONMENT": "production", "SECRET_KEY": "changeme", "INTERNAL_SECRET": ""}
    res = subprocess.run([sys.executable, "-c", "import app.main"], cwd=os.path.dirname(os.path.dirname(__file__)),
                         env=env, capture_output=True, text=True)
    assert res.returncode == 1
    assert "Config failed to load" in res.stderr and "SECRET_KEY" in res.stderr
