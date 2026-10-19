"""
Re-categorise every user's existing transactions with the current categoriser (services/recategorise.py).
Dry run by default: prints, per run, only counts (never merchants or amounts). --apply applies it; each user's run
can be undone from the app or with --undo-latest.

    python scripts/recategorise.py [--apply | --undo-latest]

Run from backend/ with DATABASE_URL set (the API role is enough: each user is bound in turn, as the API binds them).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.core.scope import all_user_ids, find_user, unbind  # noqa: E402
from app.models.categorizer import RecategorisationRun  # noqa: E402
from app.services import recategorise  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--undo-latest", action="store_true")
    args = ap.parse_args()
    totals = {"users": 0, "changed": 0, "restored": 0}
    with SessionLocal() as db:
        for uid in all_user_ids(db):
            user = find_user(db, "id", uid)
            if user is None:
                continue
            totals["users"] += 1
            if args.undo_latest:
                run = (db.query(RecategorisationRun).filter(RecategorisationRun.user_id == uid, RecategorisationRun.reverted_at.is_(None))
                       .order_by(RecategorisationRun.created_at.desc()).first())
                totals["restored"] += recategorise.undo(db, user, run) if run else 0
            elif args.apply:
                totals["changed"] += recategorise.apply(db, user).changed
            else:
                totals["changed"] += recategorise.dry_run(db, user)["changed"]
            unbind(db)
    print({"mode": "undo" if args.undo_latest else "apply" if args.apply else "dry run", **totals})


if __name__ == "__main__":
    main()
