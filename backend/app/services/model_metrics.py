"""
Live correction rate of automatic categories, as daily counts across all users: per source (model, on-device model,
known merchant, personal memory), how many transactions were categorised and how many of those the user corrected.
No user id, no merchant and no category is stored, so the table needs no row-level security. Read by
GET /internal/model-metrics (api/routes/internal.py).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import clock

TRACKED = ("model", "on_device", "known_merchant", "personal")


def source_of(explanation: Optional[dict]) -> Optional[str]:
    if not explanation or explanation.get("below_threshold"):
        return None
    source = explanation.get("source")
    if source == "model" and explanation.get("on_device"):
        return "on_device"
    return source if source in TRACKED else None


def bump(db: Session, source: Optional[str], column: str) -> None:
    """Add one to today's count. Caller commits."""
    if source is None:
        return
    assert column in ("categorised", "corrected")
    db.execute(text(f"INSERT INTO model_metrics (day, source, {column}) VALUES (:d, :s, 1) "
                    f"ON CONFLICT (day, source) DO UPDATE SET {column} = model_metrics.{column} + 1"),
               {"d": clock.today(), "s": source})


def summary(db: Session, days: int = 30) -> dict:
    since = clock.today() - timedelta(days=days - 1)
    rows = db.execute(text("SELECT source, sum(categorised), sum(corrected) FROM model_metrics WHERE day >= :d GROUP BY source"),
                      {"d": since}).all()
    out = {}
    for source, categorised, corrected in rows:
        out[source] = {"categorised": int(categorised), "corrected": int(corrected),
                       "correction_rate": round(int(corrected) / int(categorised), 4) if categorised else None}
    return {"since": since.isoformat(), "days": days, "by_source": out}
