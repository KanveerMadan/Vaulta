"""
Vaulta API — FastAPI application entry point.

Startup sequence:
  1. Validate config (fail fast on missing env vars)
  2. Verify database connection
  3. Initialize Firebase Admin SDK
  4. Mount middleware (CORS, security headers, rate limiting)
  5. Register routers

Alembic manages schema — Base.metadata.create_all() is intentionally absent.
Run migrations with: alembic upgrade head
"""

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

# ── 1. Config (fail fast) ──────────────────────────────────────────────────────
try:
    from app.core.config import settings
    logger.info(f"Config loaded | env={settings.APP_ENV}")
except Exception as e:
    logger.critical(f"Config failed to load: {e}")
    sys.exit(1)

# ── 2. Database connection check ───────────────────────────────────────────────
try:
    from app.core.database import engine
    with engine.connect() as conn:
        conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    logger.info("Database connection OK")
except Exception as e:
    logger.critical(f"Database connection failed: {e}")
    sys.exit(1)

# ── 3. Firebase Admin SDK ──────────────────────────────────────────────────────
try:
    from app.core.auth import verify_firebase_token  # noqa: F401 — triggers SDK init
    logger.info("Firebase Admin SDK initialized")
except Exception as e:
    logger.critical(f"Firebase Admin SDK init failed: {e}")
    sys.exit(1)

# ── 4. Encryption key check ────────────────────────────────────────────────────
try:
    from app.core.encryption import _get_fernet
    _get_fernet()
    logger.info("Encryption key valid")
except Exception as e:
    logger.critical(f"Encryption key invalid: {e}")
    sys.exit(1)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Vaulta API",
    description="AI-powered personal finance platform for India",
    version="0.1.0",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Security headers middleware ────────────────────────────────────────────────
from fastapi import Request
from fastapi.responses import Response

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response

# ── Routers ────────────────────────────────────────────────────────────────────
from app.api.routes import auth, transactions, csv_upload, budgets, gmail

app.include_router(auth.router)
app.include_router(transactions.router)
app.include_router(csv_upload.router)
app.include_router(budgets.router)
app.include_router(gmail.router)

# Payments router is loaded defensively: if the razorpay SDK or its
# transitive dependencies fail to import (e.g. a packaging issue),
# the rest of the app must still come up. Once Razorpay credentials
# are configured, payments.py's own route handlers raise a clean 503
# via settings.require() — but that protection only applies AFTER
# import succeeds, so the import itself is guarded here too.
try:
    from app.api.routes import payments
    app.include_router(payments.router)
    logger.info("Payments router loaded")
except Exception as e:
    logger.warning(
        f"Payments router failed to load and will be unavailable "
        f"(/api/payments/* will 404): {e}"
    )

# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "env": settings.APP_ENV}