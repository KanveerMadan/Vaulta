"""
Delete everything: the account's rows, then its Firebase login, then a confirmation email.

  1. one transaction: record a pending login deletion and delete the user row; every table cascades from it
     (transactions, people, rules, budgets, goals, chat, reports, alerts, activity, Telegram link codes and
     entries), and the user row itself held the data key, the Telegram chat id and the forwarding address
  2. delete the Firebase user (Admin SDK), retrying a few times; "no such user" counts as done
  3. send the confirmation email (when email is configured), then drop the pending record
If step 2 or 3 fails, the pending record stays (attempts, error type) and the hourly run finishes it. Meanwhile
that login can't open a new account (app/core/auth.py).
"""

from __future__ import annotations

import logging
import time

from firebase_admin import auth as firebase_auth
from sqlalchemy.orm import Session

from app.core.logs import user_ref
from app.core.scope import unbind
from app.models.deletion import PendingAuthDeletion
from app.services import email

logger = logging.getLogger(__name__)

ATTEMPTS, BACKOFF_SECONDS = 3, 0.5
SUBJECT = "Your vaulta.in account has been deleted"
TEXT = ("Your vaulta.in account and everything in it have been deleted: transactions, budgets, goals, people, rules, "
        "reports, alerts, chat history, the forwarding address and the Telegram link, and your sign-in itself.\n\n"
        "If you didn't ask for this, reply to this email.")
HTML = "<p>" + TEXT.replace("\n\n", "</p><p>") + "</p>"


def delete_account(db: Session, user) -> bool:
    """Steps 1–3. Returns True when everything, login included, is gone now; False when the login is pending."""
    pending = PendingAuthDeletion(firebase_uid=user.firebase_uid, email=user.email or None)
    db.add(pending)
    db.delete(user)
    db.commit()
    unbind(db)
    logger.info(f"deletion: account rows deleted user={user_ref(user.id)}; deleting the login")
    return complete(db, pending)


def complete(db: Session, pending: PendingAuthDeletion) -> bool:
    """Delete the Firebase user and confirm by email; on failure keep the record for the hourly run."""
    for attempt in range(ATTEMPTS):
        try:
            firebase_auth.delete_user(pending.firebase_uid)
            break
        except firebase_auth.UserNotFoundError:
            break                                      # already gone
        except Exception as e:
            pending.last_error = e.__class__.__name__[:80]
            if attempt + 1 < ATTEMPTS:
                time.sleep(BACKOFF_SECONDS * (attempt + 1))
    else:
        pending.attempts += 1
        db.commit()
        logger.warning(f"deletion: login delete failed ({pending.last_error}); pending, attempt {pending.attempts}")
        return False
    if pending.email and email.configured():
        try:
            email.send(pending.email, SUBJECT, HTML, TEXT)
        except Exception as e:
            pending.attempts += 1
            pending.last_error = e.__class__.__name__[:80]
            db.commit()
            logger.warning(f"deletion: confirmation email failed ({pending.last_error}); pending")
            return False
    db.delete(pending)
    db.commit()
    logger.info("deletion: completed (login deleted, confirmation sent)")
    return True


def complete_pending(db: Session) -> int:
    """The hourly run: finish every deletion still pending. Returns how many completed."""
    return sum(complete(db, p) for p in db.query(PendingAuthDeletion).order_by(PendingAuthDeletion.requested_at).all())


def is_pending(db: Session, firebase_uid: str) -> bool:
    return db.query(PendingAuthDeletion.id).filter(PendingAuthDeletion.firebase_uid == firebase_uid).first() is not None
