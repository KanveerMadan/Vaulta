from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Vaulta"
    ENVIRONMENT: str = "development"
    SECRET_KEY: str

    # Database
    DATABASE_URL: str

    # Firebase
    FIREBASE_SERVICE_ACCOUNT_JSON: str

    # Groq
    GROQ_API_KEY: str = ""

    # CORS
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173"

    class Config:
        env_file = ".env"
        extra = "ignore"

    def cors_origins(self) -> list[str]:
        return [i.strip() for i in self.BACKEND_CORS_ORIGINS.split(",")]

@lru_cache()
def get_settings() -> Settings:
    return Settings()