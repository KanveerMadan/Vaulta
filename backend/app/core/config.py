import re
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator

# Absolute path to backend/.env, computed from this file's own location —
# independent of the working directory the process was launched from.
# This matters because alembic is typically run from vaulta/ (repo root)
# while uvicorn/gunicorn may run from vaulta/backend/ — a relative path
# like "backend/.env" or ".env" resolves differently in each case and
# silently produces an empty config (pydantic sees {} and reports every
# required field as "missing", which is confusing to debug).
_ENV_FILE_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


# Values that must never be used as real secrets (defaults, docs, common fillers)
PLACEHOLDER_SECRETS = {
    "", "change-this-to-something-long-and-random", "changeme", "change-me", "change_me", "secret",
    "your-secret-key", "your_secret_key", "secret-key", "password", "test", "dev", "development", "placeholder",
}
MIN_SECRET_LENGTH = 32


_SECRETISH = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|DSN|DATABASE_URL|SERVICE_ACCOUNT", re.I)
DEFAULT_HOSTS = r"vercel\.app|onrender\.com|firebaseapp\.com"


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "vaulta.in"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "change-this-to-something-long-and-random"

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── Firebase ─────────────────────────────────────────────────────────────
    FIREBASE_SERVICE_ACCOUNT_JSON: str  # JSON string of service account credentials, one line

    # ── Field encryption (app/core/crypto.py) ────────────────────────────────
    # MASTER_KEY wraps each user's data key; BLIND_INDEX_KEY keys the HMAC blind indexes. Both ≥ 32 random
    # characters, required in every environment (the app refuses to start without them). Generate each with:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    # Losing MASTER_KEY makes every encrypted field unreadable: back it up outside the database. Rotate it with
    # scripts/rotate_master_key.py (docs/security/encryption.md). BLIND_INDEX_KEY can't be rotated in place.
    MASTER_KEY: str = ""
    MASTER_KEY_PREVIOUS: str = ""   # only while a rotation is running
    BLIND_INDEX_KEY: str = ""
    # Phase 4's Fernet key for the forwarding token. Read only by the encryption migration, to move any existing
    # token to the per-user keys; unused after that.
    ENCRYPTION_KEY: str = ""

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins, e.g.:
    # "https://vaulta-henna.vercel.app,http://localhost:5173"
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173"

    @field_validator("BACKEND_CORS_ORIGINS")
    @classmethod
    def origins_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("BACKEND_CORS_ORIGINS must not be empty")
        return v

    # Published at /.well-known/security.txt (also on the web app, from VITE_SECURITY_CONTACT)
    SECURITY_CONTACT_EMAIL: str = ""

    # Sensitive actions need a real sign-in this recent (seconds). Browser tests shorten it to test the prompt.
    RECENT_LOGIN_SECONDS: int = 300

    # reCAPTCHA v3, verified server-side (app/core/recaptcha.py): monitor first, then enforce (docs/go-live.md)
    RECAPTCHA_SECRET_KEY: str = ""
    RECAPTCHA_ENFORCE: bool = False
    RECAPTCHA_MIN_SCORE: float = 0.5     # below it: slowed down, never refused for the score alone
    RECAPTCHA_DEBUG_TOKEN: str = ""      # never in production

    # Merchant model (services/categorizer.py, docs/ml/model-card.md). false = the rule-based categories only.
    MERCHANT_MODEL_ENABLED: bool = True

    # New demo sessions per client IP per 10 minutes. Generous: mobile carriers put many people behind one address.
    DEMO_SESSIONS_PER_IP: int = 30

    # Optional: a full-match regex for extra origins, e.g. Vercel previews of this project:
    #   ^https://vaulta-[a-z0-9-]+-kanveer-madans-projects\.vercel\.app$
    BACKEND_CORS_ORIGIN_REGEX: str = ""

    def cors_origins(self) -> List[str]:
        """Parse comma-separated origins into a list. Strips whitespace."""
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def APP_ENV(self) -> str:
        """Alias so main.py's APP_ENV references keep working."""
        return self.ENVIRONMENT

    # ── Error monitoring (app/core/monitoring.py): off unless set ────────────
    SENTRY_DSN: str = ""

    # ── Groq (Phase 3) ───────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    # Any Groq chat model with tool calling
    GROQ_MODEL: str = "openai/gpt-oss-120b"   # llama-3.3-70b-versatile was retired by Groq (404)
    # OpenAI-compatible chat completions endpoint (browser tests point this at a local fake)
    GROQ_API_URL: str = "https://api.groq.com/openai/v1/chat/completions"

    # ── Reports by email (Resend) and the internal scheduler ────────────────
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = ""             # e.g. "vaulta.in <noreply@vaulta.in>" (a domain verified in Resend)
    APP_BASE_URL: str = "http://localhost:5173"   # frontend, for "view the full report" links
    API_BASE_URL: str = "http://localhost:8000"   # backend, for unsubscribe links
    INTERNAL_SECRET: str = ""        # X-Internal-Secret for /internal/*; unset → /internal refuses everything
    INBOUND_DOMAIN: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""     # shown in Settings ("message @…")
    TELEGRAM_WEBHOOK_SECRET: str = ""   # setWebhook secret_token; checked on every update         # alert forwarding addresses are <token>@in.<INBOUND_DOMAIN>

    # ── Razorpay (Phase 2) ───────────────────────────────────────────────────
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_PLAN_ID: str = ""  # ₹99/month plan created in Razorpay dashboard

    @model_validator(mode="after")
    def encryption_keys(self) -> "Settings":
        """MASTER_KEY and BLIND_INDEX_KEY must be real random values in every environment."""
        for name in ("MASTER_KEY", "BLIND_INDEX_KEY"):
            value = getattr(self, name)
            if value.strip().lower() in PLACEHOLDER_SECRETS or len(value) < MIN_SECRET_LENGTH:
                raise ValueError(
                    f"{name} must be set to a random value of at least {MIN_SECRET_LENGTH} characters "
                    f"(generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\")."
                )
        if self.MASTER_KEY == self.BLIND_INDEX_KEY:
            raise ValueError("MASTER_KEY and BLIND_INDEX_KEY must be different values.")
        return self

    @model_validator(mode="after")
    def production_secrets(self) -> "Settings":
        """In production, refuse to start with a missing, placeholder or short SECRET_KEY / INTERNAL_SECRET."""
        if self.ENVIRONMENT == "production":
            for name in ("SECRET_KEY", "INTERNAL_SECRET"):
                value = getattr(self, name)
                if value.strip().lower() in PLACEHOLDER_SECRETS or len(value) < MIN_SECRET_LENGTH:
                    raise ValueError(
                        f"{name} must be set to a random value of at least {MIN_SECRET_LENGTH} characters in production "
                        f"(generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\")."
                    )
            self._check_production_settings()
        return self

    def _check_production_settings(self) -> None:
        """Everything else production needs, so a misconfigured deploy fails at startup instead of at the first user."""
        problems = []
        for origin in self.cors_origins():
            if not origin.startswith("https://") or "localhost" in origin or "127.0.0.1" in origin or "*" in origin:
                problems.append(f"BACKEND_CORS_ORIGINS has {origin!r}: production origins must be https and not local")
        if self.BACKEND_CORS_ORIGIN_REGEX:
            if not (self.BACKEND_CORS_ORIGIN_REGEX.startswith("^https://") and self.BACKEND_CORS_ORIGIN_REGEX.endswith("$")):
                problems.append("BACKEND_CORS_ORIGIN_REGEX must start with ^https:// and end with $")
        for name in ("APP_BASE_URL", "API_BASE_URL"):
            url = getattr(self, name)
            if not url.startswith("https://") or "localhost" in url or "127.0.0.1" in url:
                problems.append(f"{name} must be the public https URL in production")
        # what people see (links in emails and Telegram, the sender) is on the real domain, never a host's default one
        for name in ("APP_BASE_URL", "API_BASE_URL", "EMAIL_FROM"):
            if re.search(DEFAULT_HOSTS, getattr(self, name), re.I):
                problems.append(f"{name} must use the app's own domain, not a vercel.app / onrender.com / firebaseapp.com one")
        if "@" not in self.SECURITY_CONTACT_EMAIL:
            problems.append("SECURITY_CONTACT_EMAIL must be set (it is published in /.well-known/security.txt)")
        if self.TELEGRAM_BOT_TOKEN and len(self.TELEGRAM_WEBHOOK_SECRET) < MIN_SECRET_LENGTH:
            problems.append(f"TELEGRAM_WEBHOOK_SECRET must be at least {MIN_SECRET_LENGTH} characters when the bot is configured")
        if self.RECAPTCHA_DEBUG_TOKEN:
            problems.append("RECAPTCHA_DEBUG_TOKEN must not be set in production")
        if self.RECAPTCHA_ENFORCE and not self.RECAPTCHA_SECRET_KEY:
            problems.append("RECAPTCHA_ENFORCE needs RECAPTCHA_SECRET_KEY")
        if not 0.0 <= self.RECAPTCHA_MIN_SCORE <= 1.0:
            problems.append("RECAPTCHA_MIN_SCORE must be between 0.0 and 1.0")
        if not 60 <= self.RECENT_LOGIN_SECONDS <= 600:
            problems.append("RECENT_LOGIN_SECONDS must be between 60 and 600 in production (default 300)")
        if self.MASTER_KEY_PREVIOUS and self.MASTER_KEY_PREVIOUS == self.MASTER_KEY:
            problems.append("MASTER_KEY_PREVIOUS must differ from MASTER_KEY (remove it when no rotation is running)")
        if problems:
            raise ValueError("production configuration: " + "; ".join(problems))

    def require(self, *field_names: str) -> None:
        """
        Raise a clear, actionable error if any of the named config fields are empty.
        Used by optional integrations (Razorpay) so that missing
        credentials produce a helpful 503 instead of a confusing downstream crash.
        """
        missing = [name for name in field_names if not getattr(self, name, "")]
        if missing:
            raise RuntimeError(
                f"Missing required configuration: {', '.join(missing)}. "
                f"Set these in your .env (local) or Render environment variables (production)."
            )

    def __repr_args__(self):
        # Never print a secret: a failing test, a log line or a traceback that shows the settings shows names only
        # for anything that could be a credential (a test failure printed a whole API key once, 2026-10-19).
        for name, value in super().__repr_args__():
            yield name, ("***" if value and _SECRETISH.search(name or "") else value)

    class Config:
        env_file = str(_ENV_FILE_PATH)
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()


def get_settings() -> Settings:
    """
    Accessor used by app.core.database and other modules.
    Returns the same cached Settings instance as `settings`.
    """
    return settings