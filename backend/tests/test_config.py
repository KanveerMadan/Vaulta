"""Production refuses to start without real secrets."""

import secrets

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {"DATABASE_URL": "postgresql://x@localhost/x", "FIREBASE_SERVICE_ACCOUNT_JSON": "{}",
        "MASTER_KEY": secrets.token_urlsafe(48), "BLIND_INDEX_KEY": secrets.token_urlsafe(48)}
GOOD = secrets.token_urlsafe(48)
PROD = {"ENVIRONMENT": "production", "SECRET_KEY": GOOD, "INTERNAL_SECRET": secrets.token_urlsafe(48),
        "BACKEND_CORS_ORIGINS": "https://vaulta.example", "APP_BASE_URL": "https://vaulta.example",
        "API_BASE_URL": "https://api.vaulta.example", "SECURITY_CONTACT_EMAIL": "security@vaulta.example"}


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
        make(**{**PROD, "SECRET_KEY": secret_key, "INTERNAL_SECRET": internal})


def test_production_starts_with_real_secrets():
    s = make(**PROD)
    assert s.ENVIRONMENT == "production"


@pytest.mark.parametrize("override, message", [
    ({"BACKEND_CORS_ORIGINS": "http://localhost:5173"}, "BACKEND_CORS_ORIGINS"),
    ({"BACKEND_CORS_ORIGINS": "https://vaulta.example,*"}, "BACKEND_CORS_ORIGINS"),
    ({"BACKEND_CORS_ORIGIN_REGEX": ".*"}, "BACKEND_CORS_ORIGIN_REGEX"),
    ({"APP_BASE_URL": "http://localhost:5173"}, "APP_BASE_URL"),
    ({"API_BASE_URL": "http://vaulta.example"}, "API_BASE_URL"),
    ({"APP_BASE_URL": "https://vaulta-henna.vercel.app"}, "APP_BASE_URL"),          # no default hosts users can see
    ({"API_BASE_URL": "https://vaulta-f6t8.onrender.com"}, "API_BASE_URL"),
    ({"EMAIL_FROM": "Vaulta <noreply@vaulta-a3d7a.firebaseapp.com>"}, "EMAIL_FROM"),
    ({"SECURITY_CONTACT_EMAIL": ""}, "SECURITY_CONTACT_EMAIL"),
    ({"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_WEBHOOK_SECRET": "short"}, "TELEGRAM_WEBHOOK_SECRET"),
    ({"MASTER_KEY": "x" * 40, "BLIND_INDEX_KEY": "y" * 40, "MASTER_KEY_PREVIOUS": "x" * 40}, "MASTER_KEY_PREVIOUS"),
])
def test_production_checks_urls_contacts_and_secrets(override, message):
    with pytest.raises(ValidationError, match=message):
        make(**{**PROD, **override})


@pytest.mark.parametrize("override", [{"MASTER_KEY": ""}, {"BLIND_INDEX_KEY": "short"}, {"MASTER_KEY": "changeme"}])
def test_every_environment_needs_the_encryption_keys(override):
    with pytest.raises(ValidationError, match="MASTER_KEY|BLIND_INDEX_KEY"):
        make(ENVIRONMENT="development", **override)


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


def test_production_refuses_a_recaptcha_debug_token_and_enforcing_without_a_secret():
    with pytest.raises(ValidationError, match="RECAPTCHA_DEBUG_TOKEN"):
        make(**{**PROD, "RECAPTCHA_DEBUG_TOKEN": "x"})
    with pytest.raises(ValidationError, match="RECAPTCHA_ENFORCE needs RECAPTCHA_SECRET_KEY"):
        make(**{**PROD, "RECAPTCHA_ENFORCE": True})
    with pytest.raises(ValidationError, match="RECAPTCHA_MIN_SCORE"):
        make(**{**PROD, "RECAPTCHA_MIN_SCORE": 1.5})


def test_the_launch_origins_are_accepted_and_only_they_are_allowed():
    """docs/deploy.md's BACKEND_CORS_ORIGINS for launch: the domain, www and the Vercel production URL."""
    launch = "https://vaulta.in,https://www.vaulta.in,https://vaulta-henna.vercel.app"
    s = make(**{**PROD, "BACKEND_CORS_ORIGINS": launch})
    assert s.cors_origins() == ["https://vaulta.in", "https://www.vaulta.in", "https://vaulta-henna.vercel.app"]


def test_printing_the_settings_never_shows_a_secret():
    s = make(GROQ_API_KEY="gsk_" + "x" * 40, SENTRY_DSN="https://abc@sentry.example/1", RESEND_API_KEY="re_" + "y" * 30)
    shown = repr(s) + str(s)
    for secret in ("gsk_" + "x" * 40, "https://abc@sentry.example", "re_" + "y" * 30, s.MASTER_KEY, s.BLIND_INDEX_KEY, "postgresql://x@"):
        assert secret not in shown, secret
    assert "APP_BASE_URL='http://localhost:5173'" in shown           # ordinary settings still readable
