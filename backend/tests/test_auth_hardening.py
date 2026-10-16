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


# ── Sign out everywhere (step 7) ──────────────────────────────────────────────

class FakeFirebase:
    """The Admin SDK calls Vaulta makes on a user's login, recorded."""

    def __init__(self, monkeypatch):
        import time
        self.calls = []
        self.valid_after = 0
        self.users = {}
        fb = auth.firebase_auth

        def revoke(uid):
            self.calls.append(("revoke", uid))
            self.valid_after = int(time.time()) * 1000

        class Record:
            def __init__(rec, uid):
                rec.uid = uid
                rec.tokens_valid_after_timestamp = self.valid_after
                rec.provider_data = [type("P", (), {"provider_id": p})() for p in self.users.get(uid, ["password"])]
        monkeypatch.setattr(fb, "revoke_refresh_tokens", revoke)
        monkeypatch.setattr(fb, "get_user", lambda uid: Record(uid))


def test_sign_out_everywhere_refuses_older_tokens_on_every_request(client, monkeypatch):
    import time
    fake = FakeFirebase(monkeypatch)
    old = int(time.time()) - 600
    signed_in_as(monkeypatch, iat=old, auth_time=old)
    assert client.get("/api/transactions", headers=USER).status_code == 200
    assert client.post("/api/account/sign-out-everywhere", headers=USER).status_code == 204
    assert fake.calls == [("revoke", "alice")]
    for path in ("/api/transactions", "/api/home", "/auth/me"):                    # every route, not just sensitive ones
        res = client.get(path, headers=USER)
        assert res.status_code == 401 and res.json()["detail"] == auth.SIGNED_OUT, path
    signed_in_as(monkeypatch)                                                          # a token from a new sign-in
    assert client.get("/api/transactions", headers=USER).status_code == 200
    kinds = [e["kind"] for e in client.get("/api/activity", headers=USER).json()]
    assert "signed_out_everywhere" in kinds


def test_sign_out_everywhere_leaves_telegram_and_demo_alone(client, monkeypatch):
    FakeFirebase(monkeypatch)
    from tests.conftest import user_session
    client.get("/auth/me", headers=USER)
    with user_session("alice") as (db, user):
        user.telegram_chat_id = 4242
        db.commit()
    assert client.post("/api/account/sign-out-everywhere", headers=USER).status_code == 204
    with user_session("alice") as (db, user):
        assert user.telegram_chat_id == 4242
    demo = client.post("/auth/demo").json()["token"]
    assert client.get("/api/home", headers={"Authorization": f"Bearer {demo}"}).status_code == 200


# ── Passwords (step 2) ────────────────────────────────────────────────────────

def test_change_password_needs_recent_login_policy_and_signs_out_other_sessions(client, monkeypatch):
    import time
    fake = FakeFirebase(monkeypatch)
    updates = []
    monkeypatch.setattr(auth.firebase_auth, "update_user", lambda uid, **kw: updates.append((uid, kw)))
    client.get("/auth/me", headers=USER)
    assert client.post("/api/account/password", json={"password": "short"}, headers=USER).json()["code"] == "weak_password"
    assert updates == []
    signed_in_as(monkeypatch, auth_time=int(time.time()) - 3600)
    assert client.post("/api/account/password", json={"password": "a-long-new-password"}, headers=USER).json()["code"] == "reauth_required"
    signed_in_as(monkeypatch)
    assert client.post("/api/account/password", json={"password": "a-long-new-password"}, headers=USER).status_code == 204
    assert updates == [("alice", {"password": "a-long-new-password"})] and ("revoke", "alice") in fake.calls
    signed_in_as(monkeypatch, iat=int(time.time()) + 5)                                   # this browser signed in again
    kinds = [e["kind"] for e in client.get("/api/activity", headers=USER).json()]
    assert set(kinds[:2]) == {"signed_out_everywhere", "password_changed"}          # same moment, either order


def test_a_google_account_can_add_a_password(client, monkeypatch):
    import time
    fake = FakeFirebase(monkeypatch)
    fake.users["alice"] = ["google.com"]
    monkeypatch.setattr(auth.firebase_auth, "update_user", lambda uid, **kw: None)
    signed_in_as(monkeypatch, firebase={"sign_in_provider": "google.com"})
    assert client.post("/api/account/password", json={"password": "a-long-new-password"}, headers=USER).status_code == 204
    signed_in_as(monkeypatch, firebase={"sign_in_provider": "google.com"}, iat=int(time.time()) + 5)
    events = client.get("/api/activity", headers=USER).json()
    assert {"kind": "method_linked", "detail": {"method": "password"}} in [{k: e[k] for k in ("kind", "detail")} for e in events]


def test_reset_requests_answer_the_same_for_any_address_and_log_for_the_owner(client, monkeypatch):
    client.get("/auth/me", headers=USER)
    known = client.post("/auth/password-reset-requested", json={"email": "ALICE@test.local"})
    unknown = client.post("/auth/password-reset-requested", json={"email": "nobody@test.local"})
    assert (known.status_code, known.content) == (unknown.status_code, unknown.content) == (204, b"")
    kinds = [e["kind"] for e in client.get("/api/activity", headers=USER).json()]
    assert kinds[0] == "password_reset_requested"


def test_a_completed_reset_is_noticed_at_the_next_sign_in(client, monkeypatch):
    import time
    fake = FakeFirebase(monkeypatch)
    signed_in_as(monkeypatch, auth_time=int(time.time()) - 100, iat=int(time.time()) - 100)
    client.get("/auth/me", headers=USER)
    client.post("/auth/password-reset-requested", json={"email": "alice@test.local"})
    fake.valid_after = (int(time.time()) + 1) * 1000                                  # Firebase: password was reset
    signed_in_as(monkeypatch, auth_time=int(time.time()) + 2, iat=int(time.time()) + 2)   # signs in with the new one
    kinds = [e["kind"] for e in client.get("/api/activity", headers=USER).json()]
    assert set(kinds[:2]) == {"password_reset_completed", "sign_in"}
    signed_in_as(monkeypatch, auth_time=int(time.time()) - 100, iat=int(time.time()) - 100)
    assert client.get("/api/transactions", headers=USER).status_code == 401          # sessions from before are refused


# ── Sign-in methods (step 3) ──────────────────────────────────────────────────

def test_a_linked_account_resolves_to_the_same_data(client, monkeypatch):
    signed_in_as(monkeypatch)                                                    # signed up with email + password
    client.post("/api/budgets", json={"category": "Travel", "monthly_limit": "100"}, headers=USER)
    signed_in_as(monkeypatch, firebase={"sign_in_provider": "google.com"})       # later, Google: same Firebase uid
    budgets = client.get("/api/budgets", headers=USER).json()["items"]
    assert [b["category"] for b in budgets] == ["Travel"]
    from tests.conftest import owner_engine
    from sqlalchemy import text
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 1


def test_unlinking_never_removes_the_last_method_and_signs_out(client, monkeypatch):
    import time
    fake = FakeFirebase(monkeypatch)
    deleted = []
    monkeypatch.setattr(auth.firebase_auth, "update_user", lambda uid, **kw: deleted.append(kw.get("providers_to_delete")))
    fake.users["alice"] = ["password", "google.com"]
    signed_in_as(monkeypatch)
    assert client.get("/api/account/sign-in-methods", headers=USER).json() == {"methods": ["password", "google.com"]}
    signed_in_as(monkeypatch, auth_time=int(time.time()) - 3600)
    assert client.delete("/api/account/sign-in-methods/google.com", headers=USER).json()["code"] == "reauth_required"
    signed_in_as(monkeypatch)
    assert client.delete("/api/account/sign-in-methods/google.com", headers=USER).status_code == 204
    assert deleted == [["google.com"]] and ("revoke", "alice") in fake.calls
    fake.users["alice"] = ["password"]
    signed_in_as(monkeypatch, iat=int(time.time()) + 5)
    res = client.delete("/api/account/sign-in-methods/password", headers=USER)
    assert res.status_code == 409 and res.json()["code"] == "last_method" and deleted == [["google.com"]]
    events = {e["kind"]: e["detail"] for e in client.get("/api/activity", headers=USER).json()}
    assert events["method_unlinked"] == {"method": "google.com"} and "signed_out_everywhere" in events


def test_linking_is_logged_only_when_firebase_confirms_it(client, monkeypatch):
    fake = FakeFirebase(monkeypatch)
    signed_in_as(monkeypatch)
    assert client.post("/api/account/sign-in-methods/linked", json={"method": "google.com"}, headers=USER).json()["code"] == "not_linked"
    fake.users["alice"] = ["password", "google.com"]
    assert client.post("/api/account/sign-in-methods/linked", json={"method": "google.com"}, headers=USER).status_code == 204
    assert client.get("/api/activity", headers=USER).json()[0] == {"kind": "method_linked", "detail": {"method": "google.com"},
                                                                   "at": client.get("/api/activity", headers=USER).json()[0]["at"]}


# ── Delete everything deletes the login (step 4) ──────────────────────────────

def _pending():
    from sqlalchemy import text
    from tests.conftest import owner_engine
    with owner_engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text("SELECT firebase_uid, attempts, last_error FROM pending_auth_deletions"))]


def test_delete_everything_deletes_the_login_and_confirms_by_email(client, monkeypatch, firebase_deletions):
    from app.services import email
    sent = []
    monkeypatch.setattr(email, "configured", lambda: True)
    monkeypatch.setattr(email, "send", lambda to, subject, html, text, headers=None: sent.append((to, subject)))
    client.get("/auth/me", headers=USER)
    assert client.delete("/auth/me", headers=USER).status_code == 204
    assert firebase_deletions == ["alice"]
    assert sent == [("alice@test.local", "Your Vaulta account has been deleted")]
    assert _pending() == []


def test_a_failed_login_delete_is_recorded_and_finished_by_the_hourly_run(client, monkeypatch, firebase_deletions):
    from firebase_admin import auth as firebase_auth
    from app.core.config import settings
    from app.services import deletion
    monkeypatch.setattr(deletion, "BACKOFF_SECONDS", 0)
    tries = []

    def down(uid):
        tries.append(uid)
        raise ConnectionError("Firebase unreachable")
    monkeypatch.setattr(firebase_auth, "delete_user", down)
    client.get("/auth/me", headers=USER)
    client.post("/api/budgets", json={"category": "Travel", "monthly_limit": "100"}, headers=USER)
    assert client.delete("/auth/me", headers=USER).status_code == 204              # the data is gone regardless
    assert len(tries) == deletion.ATTEMPTS
    assert _pending() == [("alice", 1, "ConnectionError")]
    res = client.get("/auth/me", headers=USER)                                      # the login can't start a new account
    assert res.status_code == 401 and res.json()["detail"] == "This account has been deleted."

    monkeypatch.setattr(firebase_auth, "delete_user", lambda uid: firebase_deletions.append(uid))
    monkeypatch.setattr(settings, "INTERNAL_SECRET", "x" * 40)
    run = client.post("/internal/run-reports", headers={"X-Internal-Secret": "x" * 40}).json()
    assert run["deletions_completed"] == 1 and firebase_deletions == ["alice"] and _pending() == []


def test_a_login_already_gone_counts_as_deleted(client, monkeypatch):
    from firebase_admin import auth as firebase_auth

    def gone(uid):
        raise firebase_auth.UserNotFoundError("no user")
    monkeypatch.setattr(firebase_auth, "delete_user", gone)
    client.get("/auth/me", headers=USER)
    assert client.delete("/auth/me", headers=USER).status_code == 204 and _pending() == []
