"""
Phase 6.5: email verification, recent-login checks, sign out everywhere, sign-in methods, deleting the login.
Firebase is replaced by tests/conftest.py's fake (token_payload); the Admin SDK calls are faked per test.
"""

import re

import pytest
from fastapi.routing import APIRoute

import app.core.auth as auth
from app.core.auth import UNVERIFIED_READS_BLOCKED, UNVERIFIED_WRITES_ALLOWED, get_current_user, get_recent_user, get_sensitive_user
from app.main import app
from tests.conftest import as_user, token_payload

USER = as_user("alice")


def _uses_session(dependant) -> bool:
    return any(d.call in (get_current_user, get_sensitive_user, get_recent_user) or _uses_session(d) for d in dependant.dependencies)


def _fill(path: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: {"card_id": "person:x", "fingerprint": "a" * 64, "provider": "google.com"}
                  .get(m[1], "00000000-0000-0000-0000-000000000000"), path)


def signed_in_as(monkeypatch, **claims):
    monkeypatch.setattr(auth, "verify_firebase_token", lambda token, check_revoked=False: token_payload(token, **claims))


def test_unverified_accounts_cannot_create_data_or_reach_out(client, monkeypatch):
    signed_in_as(monkeypatch, email_verified=False)
    assert client.get("/auth/me", headers=USER).status_code == 200                 # can sign in
    assert client.get("/api/onboarding", headers=USER).status_code == 200          # and see onboarding
    writes = sorted({(m, r.path) for r in app.routes if isinstance(r, APIRoute) and _uses_session(r.dependant)
                     for m in r.methods if m not in ("GET", "HEAD")})
    assert set(UNVERIFIED_WRITES_ALLOWED) <= set(writes), "the allowlist names a route that doesn't exist"
    checked = 0
    for method, path in writes + sorted(UNVERIFIED_READS_BLOCKED):
        if (method, path) in UNVERIFIED_WRITES_ALLOWED:
            continue
        res = client.request(method, _fill(path), headers=USER, json={})
        assert res.status_code == 403, (method, path, res.status_code, res.text)
        assert res.json()["code"] == "email_unverified", (method, path)
        checked += 1
    assert checked >= 40


def test_google_sign_ins_count_as_verified(client, monkeypatch):
    signed_in_as(monkeypatch, email_verified=False, firebase={"sign_in_provider": "google.com"})
    assert client.post("/api/budgets", json={"category": "Travel", "monthly_limit": "100"}, headers=USER).status_code == 201


def test_verifying_unlocks_the_account(client, monkeypatch):
    signed_in_as(monkeypatch, email_verified=False)
    body = {"category": "Travel", "monthly_limit": "100"}
    assert client.post("/api/budgets", json=body, headers=USER).json()["code"] == "email_unverified"
    signed_in_as(monkeypatch, email_verified=True)
    assert client.post("/api/budgets", json=body, headers=USER).status_code == 201


# ── Recent login (step 8) ─────────────────────────────────────────────────────

RECENT_ONLY = [("GET", "/api/export"), ("DELETE", "/auth/me"), ("POST", "/api/inbound/regenerate"), ("DELETE", "/api/telegram")]


def test_sensitive_routes_need_a_sign_in_from_the_last_five_minutes(client, monkeypatch):
    import time
    client.get("/auth/me", headers=USER)
    signed_in_as(monkeypatch, auth_time=int(time.time()) - auth.settings.RECENT_LOGIN_SECONDS - 5)
    assert client.get("/api/transactions", headers=USER).status_code == 200          # ordinary use is unaffected
    for method, path in RECENT_ONLY:
        res = client.request(method, path, headers=USER)
        assert res.status_code == 403, (method, path, res.status_code)
        assert res.json() == {"detail": auth.REAUTH_REQUIRED, "code": "reauth_required"}, (method, path)
    signed_in_as(monkeypatch, auth_time=int(time.time()) - 60)                       # signed in again a minute ago
    assert client.get("/api/export", headers=USER).status_code == 200
    assert client.delete("/api/telegram", headers=USER).status_code == 204


def test_routes_marked_recent_really_are(client):
    from app.core.auth import get_recent_user
    recent = {(m, r.path) for r in app.routes if isinstance(r, APIRoute)
              for m in r.methods if any(d.call is get_recent_user for d in r.dependant.dependencies)}
    assert set(RECENT_ONLY) <= recent


def test_a_failed_reauthentication_is_logged(client):
    assert client.post("/api/account/reauth-failed", headers=USER).status_code == 204
    assert [e["kind"] for e in client.get("/api/activity", headers=USER).json()][0] == "reauth_failed"
