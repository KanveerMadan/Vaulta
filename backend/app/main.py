"""
Vaulta API — FastAPI application entry point.

Startup sequence:
  1. Validate config (fail fast on missing env vars)
  2. Initialize Firebase Admin SDK
  3. Check the field-encryption keys (MASTER_KEY, BLIND_INDEX_KEY)
  4. Mount middleware (CORS, security headers)
  5. Register routers
  6. On startup, connect to the database in a background thread with
     backoff; DB-backed routes return 503 until it succeeds (core/database.py)

Alembic manages schema — Base.metadata.create_all() is intentionally absent.
Run migrations with: alembic upgrade head
"""

import logging
import sys

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")   # until config loads

# ── 1. Config (fail fast) ──────────────────────────────────────────────────────
try:
    from app.core.config import settings
    from app.core import logs
    logs.configure()                     # JSON lines from here on (app/core/logs.py)
    logger.info(f"Config loaded | env={settings.APP_ENV}")
except Exception as e:
    logger.critical(f"Config failed to load: {e}")
    sys.exit(1)

# ── 2. Firebase Admin SDK ──────────────────────────────────────────────────────
try:
    from app.core.auth import verify_firebase_token  # noqa: F401 — triggers SDK init
    logger.info("Firebase Admin SDK initialized")
except Exception as e:
    logger.critical(f"Firebase Admin SDK init failed: {e}")
    sys.exit(1)

# ── 3. Field-encryption keys (also validated by config; this proves they derive) ──
try:
    from app.core.crypto import blind_index, current_kek
    import uuid as _uuid
    current_kek()
    blind_index(_uuid.UUID(int=0), "startup check")
    logger.info("Encryption keys valid")
except Exception as e:
    logger.critical(f"Encryption keys invalid: {e}")
    sys.exit(1)

# ── App ────────────────────────────────────────────────────────────────────────
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import db_ready, wait_for_db


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=wait_for_db, name="db-connect", daemon=True).start()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Vaulta API",
    description="AI-powered personal finance platform for India",
    version="0.1.0",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_origin_regex=settings.BACKEND_CORS_ORIGIN_REGEX or None,   # Vercel preview deployments
    allow_credentials=False,             # auth is a bearer header, never cookies
    expose_headers=["X-Request-ID", "Retry-After", "Content-Disposition"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Request wrapper (app/core/logs.py), outermost: request id, user scope, security headers, body limit,
#    generic 500s, one structured log line per request ──
from app.core.logs import RequestMiddleware

app.add_middleware(RequestMiddleware)

# ── Errors the web app acts on (email_unverified, reauth_required, …): {"detail", "code"} ──
from app.core.auth import CodedError  # noqa: E402


@app.exception_handler(CodedError)
async def coded_error(_request, exc: CodedError):
    from fastapi.responses import JSONResponse as _JSON
    return _JSON(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code}, headers=exc.headers)


# ── Routers ────────────────────────────────────────────────────────────────────
from app.api.routes import auth, transactions, budgets, imports, recurring, people, rules, review, chat, settings as settings_routes, anomalies, reports, internal, unsubscribe, inbound, telegram as telegram_routes, cash as cash_routes, home, goals, alerts as alert_routes, onboarding, account

app.include_router(auth.router)
app.include_router(transactions.router)
app.include_router(budgets.router)
app.include_router(imports.router)
app.include_router(recurring.router)
app.include_router(people.router)
app.include_router(rules.router)
app.include_router(review.router)
app.include_router(chat.router)
app.include_router(settings_routes.router)
app.include_router(anomalies.router)
app.include_router(reports.router)
app.include_router(internal.router)
app.include_router(unsubscribe.router)
app.include_router(inbound.router)
app.include_router(telegram_routes.router)
app.include_router(cash_routes.router)
app.include_router(home.router)
app.include_router(goals.router)
app.include_router(alert_routes.router)
app.include_router(onboarding.router)
app.include_router(account.router)

# Payments router loaded defensively: if the Razorpay SDK or its transitive
# dependencies fail to import (e.g. a packaging issue on a fresh deploy),
# the rest of the app must still come up cleanly. Once credentials are
# configured, the route handlers raise a clean 503 via settings.require() —
# but that only applies after import succeeds, so the import itself is
# guarded here too.
try:
    from app.api.routes import payments
    app.include_router(payments.router)
    logger.info("Payments router loaded")
except Exception as e:
    logger.warning(
        f"Payments router failed to load and will be unavailable "
        f"(/api/payments/* will 404): {e}"
    )

# ── security.txt (RFC 9116) ──
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse


@app.get("/.well-known/security.txt", include_in_schema=False)
def security_txt():
    if not settings.SECURITY_CONTACT_EMAIL:
        raise HTTPException(status_code=404, detail="Not found")
    expires = (datetime.now(timezone.utc) + timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return PlainTextResponse(f"Contact: mailto:{settings.SECURITY_CONTACT_EMAIL}\nExpires: {expires}\nPreferred-Languages: en\n")


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
def health():
    """Liveness: the process is up (the database may still be connecting)."""
    return {"status": "ok", "env": settings.APP_ENV, "database": "ok" if db_ready.is_set() else "connecting"}


@app.get("/health/ready", tags=["ops"])
def health_ready():
    """
    Readiness (Render's health check): the database answers, its schema is at this code's migration head, and the
    API's database role can't bypass row-level security. 503 with the failing checks otherwise.
    """
    from sqlalchemy import text as sql
    from app.core.database import MIGRATION_HEAD, check_role, engine
    checks = {"database": "unreachable", "migrations": "unknown", "rls": "unknown"}
    try:
        with engine.connect() as conn:
            conn.execute(sql("SELECT 1"))
            checks["database"] = "ok"
            version = conn.execute(sql("SELECT version_num FROM alembic_version")).scalar()
            checks["migrations"] = "at head" if version == MIGRATION_HEAD else f"at {version}, expected {MIGRATION_HEAD}"
            checks["rls"] = "enforced" if check_role(conn) is None else "bypassed"
    except Exception as e:
        logger.warning(f"readiness check failed: {e.__class__.__name__}")
    ready = checks["database"] == "ok" and checks["migrations"] == "at head" and (
        checks["rls"] == "enforced" or settings.APP_ENV != "production")
    return JSONResponse(status_code=200 if ready else 503, content={"status": "ready" if ready else "not ready", **checks})