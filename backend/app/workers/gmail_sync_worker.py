"""
Gmail Sync Worker — Phase 2

Two Celery tasks:
  1. initial_sync_task(user_id)       — triggered immediately after OAuth connect (full_sync=True)
  2. sync_all_users_task()            — runs every 6h via Celery Beat, incremental sync for all connected users

Both tasks open their own DB session (Celery workers don't share the
FastAPI request-scoped session) and run the async sync service via asyncio.
"""

import asyncio
import logging
import uuid

from app.core.database import SessionLocal
from app.models.user import User
from app.services.gmail_sync_service import sync_gmail_for_user, GmailSyncError
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.gmail_sync_worker.initial_sync_task",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def initial_sync_task(self, user_id: str):
    """
    Full sync triggered immediately after a user connects Gmail.
    Runs once — subsequent syncs are incremental via sync_all_users_task.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
        if not user:
            logger.error(f"initial_sync_task: user {user_id} not found")
            return {"status": "error", "reason": "user_not_found"}

        result = asyncio.run(sync_gmail_for_user(db, user, full_sync=True))
        logger.info(f"Initial Gmail sync for user {user_id}: {result}")
        return {"status": "ok", **result}

    except GmailSyncError as e:
        if str(e) == "RECONNECT_REQUIRED":
            logger.warning(f"User {user_id} needs to reconnect Gmail.")
            return {"status": "reconnect_required"}
        # Transient errors — retry with backoff
        raise self.retry(exc=e)

    except Exception as e:
        logger.error(f"initial_sync_task failed for user {user_id}: {e}", exc_info=True)
        raise self.retry(exc=e)

    finally:
        db.close()


@celery_app.task(
    name="app.workers.gmail_sync_worker.sync_single_user_task",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def sync_single_user_task(self, user_id: str):
    """Incremental sync for a single user — used by sync_all_users_task fan-out."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
        if not user or not user.gmail_connected:
            return {"status": "skipped", "reason": "not_connected"}

        result = asyncio.run(sync_gmail_for_user(db, user, full_sync=False))
        logger.info(f"Incremental Gmail sync for user {user_id}: {result}")
        return {"status": "ok", **result}

    except GmailSyncError as e:
        if str(e) == "RECONNECT_REQUIRED":
            logger.warning(f"User {user_id} needs to reconnect Gmail (incremental sync).")
            return {"status": "reconnect_required"}
        raise self.retry(exc=e)

    except Exception as e:
        logger.error(f"sync_single_user_task failed for user {user_id}: {e}", exc_info=True)
        raise self.retry(exc=e)

    finally:
        db.close()


@celery_app.task(name="app.workers.gmail_sync_worker.sync_all_users_task")
def sync_all_users_task():
    """
    Celery Beat entrypoint — runs every 6 hours.
    Fans out one sync_single_user_task per Gmail-connected user.
    """
    db = SessionLocal()
    try:
        users = db.query(User.id).filter(User.gmail_connected == True).all()  # noqa: E712
        logger.info(f"Scheduling incremental Gmail sync for {len(users)} users.")
        for (user_id,) in users:
            sync_single_user_task.delay(str(user_id))
        return {"scheduled": len(users)}
    finally:
        db.close()