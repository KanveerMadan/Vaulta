"""The shared read-only demo: seed, session tokens, read-only guard on every write route, chat limits."""

import json
import re
import time
from collections import Counter
from datetime import date, timedelta

import pytest
from fastapi.routing import APIRoute

from app.core import clock
from app.core.auth import get_current_user, get_recent_user, get_sensitive_user
from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.alert import Alert
from app.models.goal import Goal
from app.models.report import Report
from app.models.transaction import Budget, Transaction
from app.services import chat, demo, llm
from tests.conftest import as_user, reset_rate_limits

TODAY = date(2024, 6, 28)

# Write routes reachable without a user session at all (their own auth); the demo can't use them as a user.
NO_SESSION = {
    ("POST", "/auth/demo"), ("POST", "/api/payments/webhook"), ("POST", "/internal/run-reports"),
    ("POST", "/internal/inbound-email"), ("POST", "/internal/telegram"), ("POST", "/unsubscribe"),
    ("POST", "/auth/password-reset-requested"),
}


@pytest.fixture(autouse=True)
def frozen(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)
    reset_rate_limits()


@pytest.fixture
def demo_headers(client):
    res = client.post("/auth/demo")
    assert res.status_code == 200, res.text
    assert res.json()["expires_in"] == 7200
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _counts():
    with SessionLocal() as db:
        user = demo.demo_user(db)
        txns = db.query(Transaction).filter(Transaction.user_id == user.id).all()
        return {
            "kinds": Counter(t.kind.value for t in txns), "cash": Counter(t.cash_flow for t in txns if t.cash_flow),
            "split": sum(t.is_split for t in txns), "months": len({t.transaction_date.strftime("%Y-%m") for t in txns}),
            "budgets": db.query(Budget).filter(Budget.user_id == user.id, Budget.is_active.is_(True)).count(),
            "goals": db.query(Goal).filter(Goal.user_id == user.id).count(),
            "reports": db.query(Report).filter(Report.user_id == user.id).count(),
            "alerts": sorted(a.type for a in db.query(Alert).filter(Alert.user_id == user.id)),
            "telegram": {a.telegram_status for a in db.query(Alert).filter(Alert.user_id == user.id)},
            "latest": max(t.transaction_date.date() for t in txns), "n": len(txns),
        }


def test_seed_has_four_months_of_everything_and_is_idempotent(client):
    with SessionLocal() as db:
        demo.seed(db)
    first = _counts()
    k = first["kinds"]
    assert first["months"] == 4 and first["latest"] <= TODAY
    assert k["spend"] > 40 and k["income"] >= 4 and k["transfer"] >= 6 and k["refund"] == 1
    assert k["lent"] == 1 and k["repayment"] == 1 and first["split"] == 1
    assert first["cash"]["withdrawal"] >= 6 and first["cash"]["spend"] >= 12
    assert (first["budgets"], first["goals"], first["reports"]) == (5, 1, 4)
    assert {"duplicate_charge", "failed_upi_unreversed", "unusual_amount"} <= set(first["alerts"])
    assert first["telegram"] == {None}                                      # demo alerts never leave the app
    with SessionLocal() as db:
        demo.seed(db)
    assert _counts() == first


def test_demo_session_reads_everything(client, demo_headers):
    home = client.get("/api/home", headers=demo_headers).json()
    assert home["safe_to_spend"]["amount"] is not None and home["outlook"]["status"] in ("green", "amber", "red")
    assert home["budgets"]["categories"] and home["coverage"]["statements"]["months"] == 4
    assert client.get("/api/goals", headers=demo_headers).json()["items"][0]["name"] == "Goa trip"
    assert client.get("/api/alerts", headers=demo_headers).json()["items"]
    assert client.get("/api/onboarding", headers=demo_headers).json()["status"] == "done"
    assert client.get("/api/reports", headers=demo_headers).status_code == 200
    assert client.get("/auth/me", headers=demo_headers).json()["email"] == "demo@vaulta.invalid"
    assert client.get("/api/inbound", headers=demo_headers).json()["address"] is None or not settings.INBOUND_DOMAIN


def test_bad_tokens(client, demo_headers):
    token = demo_headers["Authorization"].split()[1]
    forged = token[:-4] + ("0000" if not token.endswith("0000") else "1111")
    assert client.get("/api/home", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    sid, expires, sig = token[5:].split(".")
    stale = f"demo.{sid}.{int(time.time()) - 1}.{demo._sign(f'{sid}.{int(time.time()) - 1}')}"
    assert client.get("/api/home", headers={"Authorization": f"Bearer {stale}"}).status_code == 401
    assert client.get("/api/home", headers=as_user(demo.DEMO_UID)).status_code == 401   # no Firebase account can be the demo


def _uses_session(dependant) -> bool:
    return any(d.call in (get_current_user, get_sensitive_user, get_recent_user) or _uses_session(d) for d in dependant.dependencies)


def _fill(path: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: {"card_id": "person:x", "fingerprint": "a" * 64}.get(m[1], "00000000-0000-0000-0000-000000000000"), path)


def test_every_write_route_refuses_the_demo(client, demo_headers):
    """New write routes are covered automatically: anything behind a user session must 403 for the demo."""
    writes = {(m, r.path, _uses_session(r.dependant)) for r in app.routes if isinstance(r, APIRoute)
              for m in r.methods if m not in ("GET", "HEAD")}
    assert {(m, p) for m, p, session in writes if not session} == NO_SESSION
    checked = 0
    for method, path, session in sorted(writes):
        if not session:
            continue
        res = client.request(method, _fill(path), headers=demo_headers, json={})
        if (method, path) == ("POST", "/api/chat"):
            assert res.status_code != 403
            continue
        assert res.status_code == 403, (method, path, res.status_code)
        assert "demo" in res.json()["detail"] and "read-only" in res.json()["detail"]
        checked += 1
    assert checked > 40


def test_demo_chat_actions_are_read_only_and_limited(client, demo_headers, monkeypatch):
    def reply(messages, *a, **k):
        if messages[-1]["role"] == "user":
            return {"content": "", "tool_calls": [{"id": "c", "type": "function", "function": {
                "name": "set_budget", "arguments": json.dumps({"category": "Food & Dining", "amount": 9000})}}]}
        return {"content": "Confirm below."}
    monkeypatch.setattr(llm, "complete", reply)
    res = client.post("/api/chat", json={"message": "set food budget 9000"}, headers=demo_headers).json()
    [action] = res["actions"]
    assert action["read_only"] is True and "read-only" in action["note"]
    confirm = client.post("/api/chat/confirm", json={"token": action["token"], "decision": "confirm"}, headers=demo_headers)
    assert confirm.status_code == 403
    with SessionLocal() as db:
        assert db.query(Budget).filter(Budget.user_id == demo.demo_user(db).id, Budget.category == "Food & Dining").one().monthly_limit == 6000
    for _ in range(chat.DEMO_PER_MINUTE - 1):
        assert client.post("/api/chat", json={"message": "hi"}, headers=demo_headers).status_code == 200
    assert client.post("/api/chat", json={"message": "hi"}, headers=demo_headers).status_code == 429
    other = {"Authorization": f"Bearer {client.post('/auth/demo').json()['token']}"}       # another visitor
    assert client.post("/api/chat", json={"message": "hi"}, headers=other).status_code == 200


def test_hourly_run_rebuilds_the_demo_daily(client, monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_SECRET", "x" * 40)
    run = lambda: client.post("/internal/run-reports", headers={"X-Internal-Secret": "x" * 40}).json()
    assert run()["demo"] == "not created"                                 # never created → left alone
    client.post("/auth/demo")
    with SessionLocal() as db:
        first_id = demo.demo_user(db).id
    run()
    with SessionLocal() as db:
        assert demo.demo_user(db).id == first_id                          # same day: kept
    monkeypatch.setattr(clock, "today", lambda: TODAY + timedelta(days=1))
    client.post("/auth/demo")                                           # a visitor never waits for the rebuild
    with SessionLocal() as db:
        assert demo.demo_user(db).id == first_id
    assert run()["demo"] == "ready"
    with SessionLocal() as db:
        user = demo.demo_user(db)
        assert user.id != first_id and user.onboarding["demo_seeded"] == "2024-06-29"


def test_concurrent_first_visitors_get_one_complete_demo(client):
    from concurrent.futures import ThreadPoolExecutor

    def visit(_):
        with SessionLocal() as db:
            return str(demo.ensure_fresh(db, create=True).id)
    with ThreadPoolExecutor(3) as pool:
        ids = set(pool.map(visit, range(3)))
    assert len(ids) == 1
    with SessionLocal() as db:
        assert str(demo.demo_user(db).id) in ids and demo.demo_user(db).onboarding["demo_seeded"] == "2024-06-28"
    assert _counts()["months"] == 4


def test_a_visitor_waits_for_a_demo_still_being_built(client):
    """The landing page's preview can start the build; a visitor arriving mid-build must not get half a demo."""
    with SessionLocal() as db:
        user = demo.User(firebase_uid=demo.DEMO_UID, email="demo@vaulta.invalid", full_name="Demo",
                         onboarding={"status": "done"})                       # created, not yet seeded
        demo.bind_user(db, user)
        db.add(user)
        db.commit()
    token = client.post("/auth/demo").json()["token"]
    with SessionLocal() as db:
        built = demo.demo_user(db)
        assert "demo_seeded" in built.onboarding
        assert db.query(Budget).filter(Budget.user_id == built.id, Budget.category.is_(None)).count() == 1
    home = client.get("/api/home", headers={"Authorization": f"Bearer {token}"}).json()
    assert home["safe_to_spend"]["basis"] == "overall budget"
