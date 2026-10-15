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


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "Vaulta"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "change-this-to-something-long-and-random"

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── Firebase ─────────────────────────────────────────────────────────────
    FIREBASE_SERVICE_ACCOUNT_JSON: str  # JSON string of service account credentials, one line

    # ── Security ─────────────────────────────────────────────────────────────
    # Fernet symmetric encryption key for OAuth tokens stored in DB.
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # NEVER regenerate for an existing database — all stored tokens become unreadable.
    ENCRYPTION_KEY: str

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

    def cors_origins(self) -> List[str]:
        """Parse comma-separated origins into a list. Strips whitespace."""
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def APP_ENV(self) -> str:
        """Alias so main.py's APP_ENV references keep working."""
        return self.ENVIRONMENT

    # ── Groq (Phase 3) ───────────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    # Any Groq chat model with tool calling
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    # OpenAI-compatible chat completions endpoint (browser tests point this at a local fake)
    GROQ_API_URL: str = "https://api.groq.com/openai/v1/chat/completions"

    # ── Reports by email (Resend) and the internal scheduler ────────────────
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = ""             # e.g. "Vaulta <reports@yourdomain.in>" (a domain verified in Resend)
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
        return self

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