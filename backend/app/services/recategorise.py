"""
Re-categorise existing transactions with the current categoriser (services/categorizer.py): after the taxonomy
migration, or when a new model ships. Reversible and safe:

  - only automatic values change (auto_category, auto_subcategory, category_explanation); merchant names don't, so
    rules and people keep matching;
  - a transaction the user corrected in any way (user_corrected) is never touched, nor payments to people;
  - a dry run reports what would change and writes nothing;
  - an applied run keeps every row's previous values, and undo() puts them back (except on rows that changed since).
Detection then re-applies rules, refunds and people as usual.

From the app: Settings → Categories → "Re-check categories" (POST /api/categories/recategorise).
For every user: python scripts/recategorise.py [--apply] (dry run by default).
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy.orm import Session, selectinload

from app.models.categorizer import RecategorisationRun
from app.models.transaction import Transaction, TransactionNature
from app.services import categorizer
from app.services.detection import run_detection
from app.services.merchant_normalizer import normalize

FIELDS = ("auto_category", "auto_subcategory", "category_explanation")
PEER = (TransactionNature.peer_payment_sent, TransactionNature.peer_payment_received)
EXAMPLES = 10


def _values(t: Transaction) -> dict:
    return {f: getattr(t, f) for f in FIELDS}


def plan(db: Session, user) -> list[tuple[Transaction, dict, dict]]:
    """[(transaction, before, after)] for every transaction whose automatic category would change."""
    memory = categorizer.load_memory(db, user.id) if categorizer.enabled() else []
    out = []
    txns = (db.query(Transaction).options(selectinload(Transaction.source_records))
            .filter(Transaction.user_id == user.id, Transaction.split_parent_id.is_(None)).all())
    for t in txns:
        if t.user_corrected == "true" or t.transaction_nature in PEER or t.is_split:
            continue
        upi_app = any(str(getattr(r.source, "value", r.source)).startswith("upi_") for r in t.source_records)
        normalized = normalize(t.merchant_raw.replace(" ", "") if upi_app else t.merchant_raw)
        d = categorizer.categorise(t.merchant_raw, t.direction.value, normalized, memory)
        after = {"auto_category": d.category, "auto_subcategory": d.subcategory, "category_explanation": d.explanation}
        before = _values(t)
        if (before["auto_category"], before["auto_subcategory"]) != (after["auto_category"], after["auto_subcategory"]) or \
                (before["category_explanation"] or {}).get("source") != (after["category_explanation"] or {}).get("source"):
            out.append((t, before, after))
    return out


def _summary(changes) -> dict:
    return dict(Counter(f"{b['auto_category'] or 'Uncategorized'} → {a['auto_category'] or 'Uncategorized'}"
                        for _, b, a in changes).most_common())


def dry_run(db: Session, user) -> dict:
    changes = plan(db, user)
    db.rollback()
    return {"changed": len(changes), "summary": _summary(changes),
            "examples": [{"merchant": t.merchant_clean or t.merchant_raw[:40], "from": b["auto_subcategory"] or b["auto_category"],
                          "to": a["auto_subcategory"] or a["auto_category"]} for t, b, a in changes[:EXAMPLES]]}


def apply(db: Session, user) -> RecategorisationRun:
    changes = plan(db, user)
    run = RecategorisationRun(user_id=user.id, changed=len(changes), summary=_summary(changes),
                              changes=[{"id": str(t.id), "before": b, "after": a} for t, b, a in changes])
    for t, _, a in changes:
        for f, v in a.items():
            setattr(t, f, v)
    db.add(run)
    db.commit()
    run_detection(db, user)
    db.refresh(run)
    return run


def undo(db: Session, user, run: RecategorisationRun) -> int:
    """Restore the previous automatic values. Rows corrected or re-categorised since are left alone."""
    if run.reverted_at:
        return 0
    by_id = {c["id"]: c for c in run.changes}
    restored = 0
    for t in db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.id.in_([uuid.UUID(i) for i in by_id])):
        c = by_id[str(t.id)]
        if t.user_corrected == "true" or _values(t) != c["after"]:
            continue
        for f, v in c["before"].items():
            setattr(t, f, v)
        restored += 1
    run.reverted_at = datetime.now(timezone.utc)
    db.commit()
    run_detection(db, user)
    return restored
