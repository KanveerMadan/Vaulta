"""Postgres-backed rate limits (app/core/ratelimit.py): shared by every worker, keyed hashes only."""

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from app.core import ratelimit
from tests.conftest import as_user, owner_engine
from tests.test_import_batch import row

USER = as_user("alice")


def test_limit_window_and_retry_after(client):
    assert [ratelimit.hit("t", "x", 3, 60) for _ in range(5)] == [True, True, True, False, False]
    assert ratelimit.hit("t", "y", 3, 60)                                   # another key has its own count
    with owner_engine.connect() as conn:
        buckets = [b for (b,) in conn.execute(text("SELECT bucket FROM rate_limits"))]
        assert len(buckets) == 2 and all(len(b) == 64 and "x" not in b[:1] for b in buckets)
        conn.execute(text("UPDATE rate_limits SET reset_at = now() - interval '1 second'"))
        conn.commit()
    assert ratelimit.hit("t", "x", 3, 60)                                   # the window reset
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE rate_limits SET reset_at = now() - interval '1 second'"))
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        assert ratelimit.purge_expired(db) == 2


def test_counts_are_shared_across_concurrent_workers():
    with ThreadPoolExecutor(8) as pool:
        allowed = list(pool.map(lambda _: ratelimit.hit("shared", "k", 10, 60), range(40)))
    assert allowed.count(True) == 10


def test_routes_answer_429_with_retry_after(client):
    from app.core.config import settings
    for _ in range(settings.DEMO_SESSIONS_PER_IP):
        assert client.post("/auth/demo").status_code == 200
    res = client.post("/auth/demo")
    assert res.status_code == 429 and 0 < int(res.headers["retry-after"]) <= 600
    body = {"rows": [row()]}
    from app.api.routes.imports import REQUESTS_PER_HOUR
    statuses = [client.post("/api/import/batch", json=body, headers=USER).status_code for _ in range(REQUESTS_PER_HOUR + 1)]
    assert statuses[:-1] == [200] * REQUESTS_PER_HOUR and statuses[-1] == 429


def test_repeated_bad_tokens_from_one_ip_are_slowed_down(client, monkeypatch):
    import app.core.auth as auth
    from fastapi import HTTPException

    def bad(token, check_revoked=False):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    monkeypatch.setattr(auth, "verify_firebase_token", bad)
    codes = [client.get("/auth/me", headers=USER).status_code for _ in range(auth.BAD_TOKENS_PER_IP + 1)]
    assert codes[:-1] == [401] * auth.BAD_TOKENS_PER_IP and codes[-1] == 429
