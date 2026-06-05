from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import Base, engine
from app.api.routes import auth

settings = get_settings()

# Create all tables on startup (swap for Alembic migrations in production)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Vaulta API",
    description="Personal Finance AI for India",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENVIRONMENT}