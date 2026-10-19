"""
Statement uploads (Settings → Imports): list them, and delete one upload, or everything from one source (account),
after a preview of what goes. And "Reset my data": every financial row, keeping the account and its sign-in.

Deleting an upload removes its source rows. A transaction that another statement also shows (merged on import) stays,
backed by that statement; one only this upload showed is deleted, with its splits, tags and corrections. Then the
detection pass runs again, so transfers, refunds, recurring series, people links and anomalies are recomputed from
what's left; people left with no transactions and nothing the user set on them go too. Budgets and goals are
computed from transactions when shown, so they follow by themselves.
Everything filters on user_id and runs under the user's row-level security binding (two locks).
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from app.core.database import Base
from app.models.import_template import Import
from app.models.person import Person
from app.models.transaction import Transaction
from app.models.transaction_source import StatementSourceType, TransactionSourceRecord as Src
from app.services import activity


def record(db: Session, user, import_id: str, first_row) -> uuid.UUID:
    """This upload's row, created by its first batch. An id that isn't this user's is refused."""
    iid = uuid.UUID(import_id)
    db.execute(pg_insert(Import).values(id=iid, user_id=user.id, source_type=first_row.source_type,
                                        source_label=first_row.source_label).on_conflict_do_nothing(index_elements=["id"]))
    owner = db.query(Import.user_id).filter(Import.id == iid).scalar()      # another user's row is invisible (RLS)
    if owner != user.id:
        raise HTTPException(status_code=409, detail="This import id is already in use. Upload the file again.")
    return iid


def list_imports(db: Session, user) -> dict:
    real = (Src.user_id == user.id, Src.is_sample.is_(False))
    uploads = (db.query(Import, func.count(Src.id), func.min(Src.raw_date), func.max(Src.raw_date))
               .outerjoin(Src, Src.import_id == Import.id).filter(Import.user_id == user.id)
               .group_by(Import.id).order_by(Import.created_at.desc()).all())
    sources = (db.query(Src.source, Src.source_label, func.count(Src.id)).filter(*real)
               .group_by(Src.source, Src.source_label).order_by(func.count(Src.id).desc()).all())
    return {
        "uploads": [{"id": str(i.id), "source_type": i.source_type, "source_label": i.source_label,
                     "created_at": i.created_at.isoformat(), "rows": n, "first_date": a and a.isoformat(),
                     "last_date": b and b.isoformat()} for i, n, a, b in uploads if n],
        "sources": [{"source_type": s.value, "source_label": label, "rows": n} for s, label, n in sources],
    }


def _selected(db: Session, user, import_id: Optional[str], source_type: Optional[str], source_label: Optional[str]):
    q = db.query(Src).filter(Src.user_id == user.id, Src.is_sample.is_(False))
    if import_id:
        q = q.filter(Src.import_id == uuid.UUID(import_id))
    else:
        q = q.filter(Src.source == StatementSourceType(source_type),
                     Src.source_label.is_(None) if source_label is None else Src.source_label == source_label)
    return q


def _plan(db: Session, user, selected) -> tuple[list, set, set]:
    rows = selected.all()
    if not rows:
        raise HTTPException(status_code=404, detail="Nothing to delete: that import isn't in your account.")
    chosen = {r.id for r in rows}
    touched = {r.transaction_id for r in rows if r.transaction_id}
    backed_elsewhere = {t for (t,) in db.query(Src.transaction_id).filter(
        Src.user_id == user.id, Src.transaction_id.in_(touched), Src.id.notin_(chosen)).distinct()} if touched else set()
    return rows, touched - backed_elsewhere, backed_elsewhere


def preview(db: Session, user, **scope) -> dict:
    rows, gone, kept = _plan(db, user, _selected(db, user, **scope))
    return {"source_rows": len(rows), "transactions_deleted": len(gone), "transactions_kept": len(kept)}


def delete(db: Session, user, **scope) -> dict:
    from app.services.detection import run_detection
    rows, gone, kept = _plan(db, user, _selected(db, user, **scope))
    import_ids = {r.import_id for r in rows if r.import_id}
    for r in rows:
        db.delete(r)
    if gone:
        db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.split_parent_id.in_(gone)).delete(synchronize_session=False)
        db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.id.in_(gone)).delete(synchronize_session=False)
    db.flush()
    for iid in import_ids:          # an upload with no rows left is gone too
        if not db.query(Src.id).filter(Src.user_id == user.id, Src.import_id == iid).first():
            db.query(Import).filter(Import.user_id == user.id, Import.id == iid).delete(synchronize_session=False)
    db.expire_all()
    run_detection(db, user)          # transfers, refunds, recurring, people links, anomalies, alerts; commits
    merged = aliased(Person)
    orphans = (db.query(Person).filter(Person.user_id == user.id, Person.tag.is_(None), Person.default_category.is_(None),
                                       Person.default_kind.is_(None), Person.merged_into_id.is_(None),
                                       ~db.query(Transaction.id).filter(Transaction.person_id == Person.id).exists(),
                                       ~db.query(merged.id).filter(merged.merged_into_id == Person.id).exists()))
    people_removed = orphans.delete(synchronize_session=False)
    result = {"source_rows": len(rows), "transactions_deleted": len(gone), "transactions_kept": len(kept),
              "people_removed": people_removed}
    activity.record(db, user, "import_deleted", result)
    db.commit()
    return result


# The account and its sign-in (users), its security log, and how it's linked (Telegram link codes, the Gmail
# forwarding confirmation) stay; every other table with a user_id is the user's financial data.
KEEP_ON_RESET = {"users", "activity_log", "telegram_link_codes", "gmail_confirmations"}


def reset_data(db: Session, user) -> dict:
    counts = {}
    for table in reversed(Base.metadata.sorted_tables):            # children before parents
        if "user_id" in table.c and table.name not in KEEP_ON_RESET:
            n = db.execute(table.delete().where(table.c.user_id == user.id)).rowcount
            if n:
                counts[table.name] = n
    activity.record(db, user, "data_reset", {"transactions": counts.get("transactions", 0)})
    db.commit()
    return counts
