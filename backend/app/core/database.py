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


def wait_for_db(max_delay: float = 30.0) -> None:
    """Block until the database answers SELECT 1, retrying with exponential backoff."""
    delay = 1.0
    while not db_ready.is_set():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ready.set()
            logger.info("Database connection OK")
        except Exception as e:
            logger.warning(f"Database unreachable ({e.__class__.__name__}: {e}); retrying in {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 2, max_delay)


# Dependency — use this in every route
def get_db():
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
