"""
Celery application — Phase 2

Configures Celery with Redis as broker and result backend, plus a beat schedule
for 6-hourly Gmail incremental syncs.

Run locally:
    celery -A app.workers.celery_app worker --loglevel=info
    celery -A app.workers.celery_app beat --loglevel=info

On Render: create a separate "Background Worker" service running the worker
command above, and a "Cron Job" or second worker with `beat` for scheduling.
Both must share the same REDIS_URL as the web service.
"""

import logging

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

logger = logging.getLogger(__name__)

if not settings.REDIS_URL:
    logger.warning(
        "REDIS_URL is not set — Celery app will fail to connect to broker. "
        "Background sync jobs (Gmail 6-hourly sync) will not run until configured."
    )

celery_app = Celery(
    "vaulta",
    broker=settings.REDIS_URL or "redis://localhost:6379/0",
    backend=settings.REDIS_URL or "redis://localhost:6379/0",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",  # Vaulta is India-focused — schedule times are IST
    enable_utc=True,
    task_track_started=True,
    # Retry transient failures (network blips to Gmail/Razorpay) with backoff
    task_default_retry_delay=60,  # seconds
    task_max_retries=3,
)

# Auto-discover tasks in app.workers.*
celery_app.autodiscover_tasks(["app.workers"])

# ── Beat schedule ────────────────────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    "gmail-incremental-sync-every-6-hours": {
        "task": "app.workers.gmail_sync_worker.sync_all_users_task",
        "schedule": crontab(minute=0, hour="0,6,12,18"),  # 00:00, 06:00, 12:00, 18:00 IST
    },
}