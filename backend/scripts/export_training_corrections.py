"""
Exports the category corrections of users who opted in (Settings → Categories, users.ml_training_consent) for
retraining the merchant model (ml/retrain.py). For each corrected transaction: its stored narration (already
stripped of personal details at import) and the subcategory the user chose. Nothing else: no amounts, dates, user
ids or people. Corrections to the user's own custom subcategories are left out (they mean nothing to the model).

    python scripts/export_training_corrections.py [--out ../ml/data/private/corrections.jsonl]

Run from backend/ with DATABASE_URL set. The output belongs in ml/data/private/ (git-ignored) and is never printed;
the script prints counts only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.core.scope import all_user_ids, find_user, unbind  # noqa: E402
from app.models.correction import Correction  # noqa: E402
from app.models.transaction import Transaction, TransactionNature  # noqa: E402
from app.services import taxonomy  # noqa: E402

PEER = (TransactionNature.peer_payment_sent, TransactionNature.peer_payment_received)


def collect(db, user) -> list[dict]:
    latest = {}
    for c in (db.query(Correction).filter(Correction.user_id == user.id, Correction.field == "subcategory")
              .order_by(Correction.created_at)):
        latest[c.transaction_id] = c.new_value
    keep = {tid: v for tid, v in latest.items() if v in taxonomy.SUBCATEGORIES}
    if not keep:
        return []
    rows = db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.id.in_(list(keep)))
    return [{"text": t.merchant_raw, "label": keep[t.id], "source": "correction"} for t in rows if t.transaction_nature not in PEER]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "ml" / "data" / "private" / "corrections.jsonl")
    args = ap.parse_args()
    out, users, consenting = {}, 0, 0
    with SessionLocal() as db:
        for uid in all_user_ids(db):
            user = find_user(db, "id", uid)
            if user is None:
                continue
            users += 1
            if user.ml_training_consent:
                consenting += 1
                for r in collect(db, user):
                    out[r["text"].lower()] = r          # one label per narration: the latest export wins
            unbind(db)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out.values()))
    print({"users": users, "consenting": consenting, "corrections": len(out)})


if __name__ == "__main__":
    main()
