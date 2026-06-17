from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator

# Absolute path to backend/.env, computed from this file's own location —
# independent of the working directory the process was launched from.
# This matters because alembic is typically run from vaulta/ (repo root)
# while uvicorn/gunicorn may run from vaulta/backend/ — a relative path
# like "backend/.env" or ".env" resolves differently in each case and
# silently produces an empty config (pydantic sees {} and reports every
# required field as "missing", which is confusing to debug).
_ENV_FILE_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


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

    # ── Razorpay (Phase 2) ───────────────────────────────────────────────────
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_PLAN_ID: str = ""  # ₹99/month plan created in Razorpay dashboard

    # ── Redis / Celery (Phase 2) ──────────────────────────────────────────────
    REDIS_URL: str = ""

    # ── Gmail OAuth (Phase 2) ────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""

    def require(self, *field_names: str) -> None:
        """
        Raise a clear, actionable error if any of the named config fields are empty.
        Used by Phase 2 services (Gmail OAuth, Razorpay, Celery) so that missing
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