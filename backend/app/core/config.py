from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator


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

    # ── Redis / Celery (Phase 2) ──────────────────────────────────────────────
    REDIS_URL: str = ""

    # ── Gmail OAuth (Phase 2) ────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""

    class Config:
        env_file = "backend/.env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()


def get_settings() -> Settings:
    """
    Accessor used by app.core.database and other modules.
    Returns the same cached Settings instance as `settings`.
    """
    return settings