"""
Rate limits shared by every API worker, kept in Postgres (table rate_limits; no Redis).

Each bucket is a counter with a window that starts at its first hit: `limit` hits are allowed until the window
resets. The bucket name is stored only as a keyed hash (BLIND_INDEX_KEY), so the table holds no IPs, user ids or
chat ids. Counting runs on its own short transaction, so a request that fails afterwards still counts.
Expired buckets are deleted by the hourly run (purge_expired).

  hit("telegram", chat_id, limit=20, window=60) → True if allowed
  Depends(per_user("import", 60, 3600))         → 429 with Retry-After once a user goes over
  Depends(per_ip("demo", 10, 600))              → the same, per client IP
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text

from app.core.crypto import lookup_hash

_HIT = text("""
INSERT INTO rate_limits (bucket, hits, reset_at) VALUES (:b, 1, now() + make_interval(secs => :w))
ON CONFLICT (bucket) DO UPDATE SET
  hits = CASE WHEN rate_limits.reset_at <= now() THEN 1 ELSE rate_limits.hits + 1 END,
  reset_at = CASE WHEN rate_limits.reset_at <= now() THEN EXCLUDED.reset_at ELSE rate_limits.reset_at END
RETURNING hits, reset_at
""")


class RateLimited(HTTPException):
    def __init__(self, retry_after: int, message: str = "Too many requests. Try again in a little while."):
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=message,
                         headers={"Retry-After": str(max(1, retry_after))})


def _count(name: str, who, window: int) -> tuple[int, int]:
    from app.core.database import engine
    with engine.begin() as conn:
        hits, reset_at = conn.execute(_HIT, {"b": lookup_hash("rate", f"{name}|{who}"), "w": window}).one()
    return hits, math.ceil((reset_at - datetime.now(timezone.utc)).total_seconds())


def hit(name: str, who, limit: int, window: int) -> bool:
    """Count one hit for (name, who); False once there have been more than `limit` in the window."""
    hits, _ = _count(name, who, window)
    return hits <= limit


def check(name: str, who, limit: int, window: int, message: str | None = None) -> None:
    """Count one hit; raise RateLimited (429, Retry-After) when over the limit."""
    hits, retry_after = _count(name, who, window)
    if hits > limit:
        raise RateLimited(retry_after, message) if message else RateLimited(retry_after)


def client_ip(request: Request) -> str:
    # Behind Render's proxy, uvicorn runs with --proxy-headers so this is the client's address
    return request.client.host if request.client else "unknown"


def per_user(name: str, limit: int, window: int, user_dependency=None):
    from app.core.auth import get_current_user
    dependency = user_dependency or get_current_user

    def limiter(user=Depends(dependency)):
        check(name, user.id, limit, window)
    return limiter


def per_ip(name: str, limit: int, window: int):
    def limiter(request: Request):
        check(name, client_ip(request), limit, window)
    return limiter


def purge_expired(db) -> int:
    n = db.execute(text("DELETE FROM rate_limits WHERE reset_at < now()")).rowcount
    db.commit()
    return n
