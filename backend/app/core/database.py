import logging
import threading
import time

from fastapi import HTTPException, status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # drops dead connections automatically
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

# Set once the first successful connection is made. Until then DB routes
# return 503 instead of the process exiting (cold-start Postgres on Render/Neon).
db_ready = threading.Event()
# Set when the API's database role could see past row-level security (superuser, BYPASSRLS or the tables' owner).
# In production every DB route then refuses with 503: the role must be vaulta_app (docs/security/row-level-security.md).
db_role_problem: list[str] = []


def check_role(conn) -> str | None:
    """Why this connection's role would bypass row-level security, or None if it can't."""
    role, superuser, bypass = conn.execute(text(
        "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
    owns = conn.execute(text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner = current_user")).scalar()
    if superuser or bypass or owns:
        what = "a superuser" if superuser else "BYPASSRLS" if bypass else f"the owner of {owns} tables"
        return f"the API connects as {role}, which is {what}; row-level security would not apply"
    return None


def wait_for_db(max_delay: float = 30.0) -> None:
    """Block until the database answers SELECT 1, retrying with exponential backoff."""
    delay = 1.0
    while not db_ready.is_set():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                problem = check_role(conn)
            if problem and settings.ENVIRONMENT == "production":
                db_role_problem.append(problem)
                logger.critical(f"Refusing database requests: {problem}")
            elif problem:
                logger.warning(f"{problem} (allowed outside production)")
            db_ready.set()
            logger.info("Database connection OK")
        except Exception as e:
            logger.warning(f"Database unreachable ({e.__class__.__name__}); retrying in {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 2, max_delay)


# Dependency — use this in every route
def get_db():
    if db_role_problem:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The service is misconfigured.")
    if not db_ready.is_set():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is starting up. Please retry in a few seconds.",
        )
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
