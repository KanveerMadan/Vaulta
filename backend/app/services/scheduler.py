"""
Hourly report run (POST /internal/run-reports, called by the Render cron job).

For each user, in their own timezone, the report due is the most recent
period whose send time has passed:
  weekly   Monday–Sunday, sent Sunday 19:00 (the week ending that day)
  monthly  the previous month, sent on the 1st at 09:00
  annual   the previous year, sent on 1 January at 09:00
Idempotent: a report is built only if it doesn't exist yet, and emailed only
if it hasn't been (so a failed send is retried next hour). Periods with no
transactions are skipped. Also: date-based alerts and alerts held for quiet
hours (services/alerts.py), and purges chat history older than 30 days.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import clock
from app.models.report import Report
from app.models.transaction import Transaction
from app.models.user import User
from app.services import alerts, analytics, demo, email, report_email, reports
from app.services.chat import purge_old
from app.services.telegram_bot import send_cash_reminder, send_weekly_summary

logger = logging.getLogger(__name__)

WEEKLY_SEND = time(19, 0)     # Sunday
MONTHLY_SEND = time(9, 0)     # on the 1st
ANNUAL_SEND = time(9, 0)      # on 1 January
PERIOD_TYPES = ("weekly", "monthly", "annual")


def user_zone(user: User):
    return clock.zone(user.timezone)


def due_day(period_type: str, local_now: datetime) -> date:
    """A day inside the period whose report is due at `local_now` (the user's local time)."""
    today = local_now.date()
    if period_type == "weekly":
        sunday = today + timedelta(days=6 - today.weekday())
        if local_now >= datetime.combine(sunday, WEEKLY_SEND, tzinfo=local_now.tzinfo):
            return sunday                      # the week ending tonight
        return sunday - timedelta(days=7)      # the week that ended last Sunday
    if period_type == "monthly":
        first = today.replace(day=1)
        if local_now >= datetime.combine(first, MONTHLY_SEND, tzinfo=local_now.tzinfo):
            return first - timedelta(days=1)
        return (first - timedelta(days=1)).replace(day=1) - timedelta(days=1)
    jan1 = date(today.year, 1, 1)
    if local_now >= datetime.combine(jan1, ANNUAL_SEND, tzinfo=local_now.tzinfo):
        return date(today.year - 1, 12, 31)
    return date(today.year - 2, 12, 31)


def _has_activity(db: Session, user: User, start: date, end: date) -> bool:
    return db.query(Transaction.id).filter(*analytics.counted(user.id, start, end)).first() is not None


def _send(db: Session, user: User, report: Report, now: datetime) -> bool:
    if report.emailed_at or not getattr(user, f"email_{report.period_type}") or not user.email or not email.configured():
        return False
    subject, html, text, headers = report_email.render(report, user)
    email.send(user.email, subject, html, text, headers)
    report.emailed_at = now
    db.commit()
    return True


def run(db: Session, now: Optional[datetime] = None) -> dict:
    now = now or clock.now()
    result = {"users": 0, "generated": 0, "emailed": 0, "telegram": 0, "cash_reminders": 0, "alerts": 0, "alerts_sent": 0,
              "skipped_empty": 0, "errors": 0}
    for user in db.query(User).order_by(User.created_at):
        result["users"] += 1
        local_now = now.astimezone(user_zone(user))
        try:
            done = alerts.run_hourly(db, user, now)
            result["alerts"] += done["new"]
            result["alerts_sent"] += done["telegram_sent"]
        except Exception as e:
            db.rollback()
            result["errors"] += 1
            logger.error(f"alerts: user={user.id} failed: {e.__class__.__name__}: {e}")
        try:
            if local_now.weekday() == 6 and local_now.time() >= WEEKLY_SEND and send_cash_reminder(db, user):
                result["cash_reminders"] += 1
        except Exception as e:
            db.rollback()
            result["errors"] += 1
            logger.error(f"cash reminder: user={user.id} failed: {e.__class__.__name__}: {e}")
        for period_type in PERIOD_TYPES:
            if not getattr(user, f"reports_{period_type}"):
                continue
            try:
                start, end = reports.period_for(period_type, due_day(period_type, local_now))
                existing = db.query(Report).filter(Report.user_id == user.id, Report.period_type == period_type,
                                                   Report.period_start == start).first()
                if existing is None:
                    if not _has_activity(db, user, start, end):
                        result["skipped_empty"] += 1
                        continue
                    existing, _ = reports.generate(db, user.id, period_type, start)
                    result["generated"] += 1
                if _send(db, user, existing, now):
                    result["emailed"] += 1
                if period_type == "weekly" and send_weekly_summary(db, user, existing):
                    result["telegram"] += 1
            except Exception as e:   # one user's failure mustn't stop everyone else's reports
                db.rollback()
                result["errors"] += 1
                logger.error(f"report run: user={user.id} type={period_type} failed: {e.__class__.__name__}: {e}")
    try:
        result["demo"] = "ready" if demo.ensure_fresh(db) else "not created"   # daily rebuild, once it exists
    except Exception as e:
        db.rollback()
        result["errors"] += 1
        logger.error(f"demo reseed failed: {e.__class__.__name__}: {e}")
    result["chat_messages_purged"] = purge_old(db)
    return result
