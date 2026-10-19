"""
Sample rows (the preview layer, core/samples.py): clearing them, and deleting them an hour after they were made.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core import clock
from app.core.samples import INCLUDE
from app.models.transaction import Transaction
from app.models.transaction_source import TransactionSourceRecord

LIFETIME = timedelta(hours=1)


def _delete(db: Session, user_id, older_than=None) -> int:
    q = db.query(Transaction).execution_options(**{INCLUDE: True}).filter(Transaction.user_id == user_id,
                                                                         Transaction.is_sample.is_(True))
    if older_than is not None:
        q = q.filter(Transaction.created_at < older_than)
    ids = [t.id for t in q.with_entities(Transaction.id)]
    if not ids:
        return 0
    db.query(TransactionSourceRecord).execution_options(**{INCLUDE: True}).filter(
        TransactionSourceRecord.user_id == user_id, TransactionSourceRecord.is_sample.is_(True),
        TransactionSourceRecord.transaction_id.in_(ids)).delete(synchronize_session=False)
    db.query(Transaction).execution_options(**{INCLUDE: True}).filter(Transaction.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return len(ids)


def clear(db: Session, user) -> int:
    """Delete all of the user's sample rows now ("Clear samples")."""
    return _delete(db, user.id)


def purge_expired(db: Session, user) -> int:
    """Delete the user's sample rows made more than LIFETIME ago (the hourly run, and lazily on reads)."""
    return _delete(db, user.id, clock.now() - LIFETIME)


def count(db: Session, user) -> int:
    return (db.query(Transaction.id).execution_options(**{INCLUDE: True})
            .filter(Transaction.user_id == user.id, Transaction.is_sample.is_(True)).count())
