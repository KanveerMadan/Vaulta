"""
Re-wrap every user's data key with a new MASTER_KEY. Only the wrapped keys in users.data_key change; no encrypted
field is touched, so it is quick and safe to run while the API serves traffic.

    MASTER_KEY=<new> MASTER_KEY_PREVIOUS=<old> python scripts/rotate_master_key.py [--dry-run]

Run from backend/ with the database owner's URL in MIGRATION_DATABASE_URL (or DATABASE_URL). Commits every BATCH
users and skips keys already wrapped by the new MASTER_KEY, so it can be stopped and re-run at any point.
The full procedure (deploy order, when to drop MASTER_KEY_PREVIOUS) is in docs/security/encryption.md.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core import crypto  # noqa: E402
from app.core.config import settings  # noqa: E402

BATCH = 200


def rotate(engine, dry_run: bool = False) -> dict:
    if not settings.MASTER_KEY_PREVIOUS:
        raise SystemExit("Set MASTER_KEY_PREVIOUS to the old key (and MASTER_KEY to the new one).")
    new = crypto.current_kek()
    counts = {"rewrapped": 0, "already_current": 0}
    last = "00000000-0000-0000-0000-000000000000"
    while True:
        with engine.begin() as conn:
            rows = conn.execute(text("SELECT id, data_key FROM users WHERE data_key IS NOT NULL AND id > :last "
                                     "ORDER BY id LIMIT :n"), {"last": last, "n": BATCH}).all()
            if not rows:
                return counts
            for uid, wrapped in rows:
                last = uid
                if crypto.wrapped_by_current(wrapped):
                    counts["already_current"] += 1
                    continue
                rewrapped = crypto.wrap(crypto.unwrap(wrapped, uid), uid, new)
                counts["rewrapped"] += 1
                if not dry_run:
                    conn.execute(text("UPDATE users SET data_key = :k WHERE id = :u"), {"k": rewrapped, "u": uid})


if __name__ == "__main__":
    url = os.environ.get("MIGRATION_DATABASE_URL") or settings.DATABASE_URL
    result = rotate(create_engine(url), dry_run="--dry-run" in sys.argv)
    print(("dry run: " if "--dry-run" in sys.argv else "") + ", ".join(f"{k} {v}" for k, v in result.items()))
