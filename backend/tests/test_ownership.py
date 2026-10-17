"""
A user cannot read, edit or delete another user's data through any route.
test_every_route_is_covered fails if a user-data route is added without a
case here.
"""

import uuid

from fastapi.routing import APIRoute

from app.main import app
from tests.conftest import as_user
from tests.test_import_batch import row
from tests.test_manual_entry import manual

ALICE, BOB = as_user("alice"), as_user("bob")

COVERED = {
    ("GET", "/api/transactions"),
    ("GET", "/api/transactions/summary"),
    ("POST", "/api/transactions"),
    ("POST", "/api/transactions/reanalyze"),
    ("POST", "/api/transactions/{transaction_id}/split"),     # tests/test_splits.py::test_split_is_per_user
    ("DELETE", "/api/transactions/{transaction_id}/split"),
    ("PATCH", "/api/transactions/{transaction_id}"),
    ("DELETE", "/api/transactions/{transaction_id}"),
    ("POST", "/api/import/batch"),
    ("GET", "/api/import/templates/{fingerprint}"),
    ("PUT", "/api/import/templates/{fingerprint}"),
    ("GET", "/api/recurring"),
    ("PATCH", "/api/recurring/{series_id}"),
    ("POST", "/api/recurring/refresh"),
    ("GET", "/api/people"),            # tests/test_people.py::test_person_validation_and_isolation
    ("PATCH", "/api/people/{person_id}"),
    ("POST", "/api/people/{person_id}/merge"),   # tests/test_people.py::test_merge_validation_and_isolation
    ("GET", "/api/rules"),             # tests/test_rules.py::test_rules_are_per_user
    ("POST", "/api/rules"),
    ("PATCH", "/api/rules/{rule_id}"),
    ("DELETE", "/api/rules/{rule_id}"),
    ("GET", "/api/review"),            # tests/test_review.py::test_review_is_per_user
    ("POST", "/api/review/{card_id}/answer"),
    ("GET", "/api/budgets"),           # test_bob_cannot_touch_alice_budgets below
    ("GET", "/api/budgets/status"),
    ("POST", "/api/budgets"),
    ("PATCH", "/api/budgets/{budget_id}"),
    ("DELETE", "/api/budgets/{budget_id}"),
    # tests/test_chat.py: confirm tokens are bound to their user, history is per user
    ("POST", "/api/chat"),
    ("POST", "/api/chat/confirm"),
    ("GET", "/api/chat/history"),
    ("DELETE", "/api/chat/history"),
    # tests/test_chat.py::test_ai_chat_toggle (one user's setting doesn't affect another)
    ("GET", "/api/settings"),
    ("PATCH", "/api/settings"),
    # tests/test_anomalies.py::test_dismiss_via_review_persists_and_is_per_user
    ("GET", "/api/anomalies"),
    ("PATCH", "/api/anomalies/{anomaly_id}"),
    # tests/test_reports.py::test_reports_are_idempotent_and_per_user
    ("GET", "/api/reports"),
    ("GET", "/api/reports/{report_id}"),
    ("POST", "/api/reports/generate"),
    # tests/test_account.py::test_export_and_activity_are_per_user
    ("GET", "/api/export"),
    ("GET", "/api/activity"),
    ("POST", "/api/account/reauth-failed"),   # writes only to the caller's own activity log
    ("POST", "/api/account/sign-out-everywhere"),   # acts on the caller's own Firebase login (test_auth_hardening.py)
    ("POST", "/api/account/password"),              # the caller's own login (test_auth_hardening.py)
    ("GET", "/api/account/sign-in-methods"), ("POST", "/api/account/sign-in-methods/linked"),
    ("DELETE", "/api/account/sign-in-methods/{provider}"),   # the caller's own login (test_auth_hardening.py)
    # tests/test_inbound.py::test_addresses_are_per_user
    ("GET", "/api/inbound"),
    ("POST", "/api/inbound/regenerate"),
    ("POST", "/api/inbound/gmail-confirmation/dismiss"),
    # tests/test_telegram.py::test_other_users_entries_are_not_reachable / test_link_codes_…
    ("GET", "/api/telegram"),
    ("POST", "/api/telegram/link-code"),
    ("PATCH", "/api/telegram"),
    ("DELETE", "/api/telegram"),
    # tests/test_cash.py::test_wallet_is_per_user
    ("GET", "/api/cash"),
    ("POST", "/api/cash/declare"),
    ("POST", "/api/cash/reconcile"),
    # tests/test_home.py::test_home_is_per_user
    ("GET", "/api/home"),
    # tests/test_goals.py::test_goals_are_per_user
    ("GET", "/api/goals"),
    ("POST", "/api/goals"),
    ("PATCH", "/api/goals/{goal_id}"),
    ("DELETE", "/api/goals/{goal_id}"),
    ("POST", "/api/goals/{goal_id}/entries"),
    ("DELETE", "/api/goals/{goal_id}/entries/{entry_id}"),
    # tests/test_alerts.py::test_bell_unread_and_isolation
    ("GET", "/api/alerts"),
    ("POST", "/api/alerts/read"),
    # tests/test_onboarding.py (state is the caller's own; Bob never sees Alice's)
    ("GET", "/api/onboarding"),
    ("PATCH", "/api/onboarding"),
    ("POST", "/api/onboarding/test-email"),
    # tests/test_taxonomy.py::test_custom_subcategories / test_tags_filter_totals_and_isolation
    ("GET", "/api/categories"),
    ("POST", "/api/categories/subcategories"),
    ("DELETE", "/api/categories/subcategories/{subcategory_id}"),
    ("GET", "/api/tags"),
    ("DELETE", "/api/tags/{tag_id}"),
    # tests/test_categorizer.py::test_explanations_and_recategorising_are_per_user
    ("GET", "/api/transactions/{transaction_id}/explanation"),
    ("POST", "/api/categories/recategorise"),
    ("POST", "/api/categories/recategorise/{run_id}/undo"),
}
# Routes that only ever act on the caller's own user row (no id in the path)
# or on no user at all. Listed so the guard still notices new routes.
EXEMPT = {
    ("GET", "/auth/me"), ("PATCH", "/auth/me"), ("DELETE", "/auth/me"),
    ("POST", "/auth/demo"),        # no user: issues a demo session token (tests/test_demo.py)
    ("POST", "/api/payments/create-subscription"), ("GET", "/api/payments/status"),
    ("POST", "/api/payments/webhook"),    # no user; Razorpay HMAC signature instead
    # no user session: X-Internal-Secret (tests/test_delivery.py::test_internal_endpoint_needs_the_secret)
    ("POST", "/internal/run-reports"),
    ("GET", "/internal/model-metrics"),     # aggregate counts only (tests/test_categorizer.py)
    ("POST", "/internal/inbound-email"),   # tests/test_inbound.py::test_endpoint_guards
    ("POST", "/internal/telegram"),        # Telegram's secret_token header: tests/test_telegram.py::test_webhook_secret
    # no user session: signed per-user token (tests/test_delivery.py::test_unsubscribe)
    ("GET", "/unsubscribe"), ("POST", "/unsubscribe"),
    ("GET", "/.well-known/security.txt"),   # public, no data (tests/test_app_security.py)
    ("GET", "/health/ready"),               # public status only (tests/test_health.py)
    ("POST", "/auth/password-reset-requested"),   # no user; same answer for any address (test_auth_hardening.py)
}


def test_every_route_is_covered():
    routes = {(method, r.path) for r in app.routes if isinstance(r, APIRoute) for method in r.methods} - {("GET", "/health")}
    assert routes - EXEMPT == COVERED


def _alice_data(client):
    manual_txn = client.post("/api/transactions", json=manual(client_id="11111111-1111-1111-1111-111111111111"),
                             headers=ALICE).json()
    client.post("/api/import/batch", json={"rows": [row()]}, headers=ALICE)
    items = client.get("/api/transactions", headers=ALICE).json()["items"]
    assert len(items) == 2
    return manual_txn, next(i for i in items if i["id"] != manual_txn["id"])


def test_bob_cannot_read_alice(client):
    _alice_data(client)
    assert client.get("/api/transactions", headers=BOB).json() == {"items": [], "total": 0, "page": 1, "page_size": 50, "has_more": False}
    for period in ("month", "year", "lifetime"):
        summary = client.get(f"/api/transactions/summary?period={period}&year=2024&month=3", headers=BOB).json()
        assert summary["transaction_count"] == 0 and summary["total_spend"] == "0.00", period


def test_bob_cannot_edit_or_delete_alice(client):
    manual_txn, imported = _alice_data(client)
    for txn in (manual_txn, imported):
        assert client.patch(f"/api/transactions/{txn['id']}", json={"category": "Travel", "notes": "bob"}, headers=BOB).status_code == 404
        assert client.delete(f"/api/transactions/{txn['id']}", headers=BOB).status_code == 404
    after = {i["id"]: i for i in client.get("/api/transactions", headers=ALICE).json()["items"]}
    assert after[manual_txn["id"]]["category"] == "Transport" and after[manual_txn["id"]]["notes"] is None
    assert after[imported["id"]]["user_corrected"] is None
    assert len(after) == 2


def test_bob_cannot_reach_alice_through_ingestion(client):
    manual_txn, imported = _alice_data(client)
    # Same client_id as Alice's manual entry → Bob gets his own row, not hers
    bobs = client.post("/api/transactions", json=manual(client_id="11111111-1111-1111-1111-111111111111"), headers=BOB).json()
    assert bobs["id"] != manual_txn["id"] and bobs["user_id"] != manual_txn["user_id"]
    # Same UTR / same content as Alice's import → not merged into her transaction
    assert client.post("/api/import/batch", json={"rows": [row()]}, headers=BOB).json()["imported"] == 1
    assert client.get("/api/transactions", headers=ALICE).json()["total"] == 2
    assert client.get("/api/transactions", headers=BOB).json()["total"] == 2


def test_bob_cannot_read_alice_templates(client):
    fp = "b" * 64
    body = {"column_count": 3, "source_type": "bank_csv", "mapping": {
        "date": 0, "description": 1, "amount": 2, "date_format": "%d/%m/%Y", "amount_sign": "negative_is_debit"}}
    assert client.put(f"/api/import/templates/{fp}", json=body, headers=ALICE).status_code == 200
    assert client.get(f"/api/import/templates/{fp}", headers=BOB).status_code == 404
    # Bob writing the same fingerprint creates his own, Alice's is unchanged
    client.put(f"/api/import/templates/{fp}", json={**body, "column_count": 9}, headers=BOB)
    assert client.get(f"/api/import/templates/{fp}", headers=ALICE).json()["column_count"] == 3


def test_random_ids_are_404(client):
    _alice_data(client)
    assert client.patch(f"/api/transactions/{uuid.uuid4()}", json={"notes": "x"}, headers=ALICE).status_code == 404


def test_bob_reanalyze_leaves_alice_alone(client):
    manual_txn, imported = _alice_data(client)
    client.patch(f"/api/transactions/{imported['id']}", json={"kind": "lent"}, headers=ALICE)
    before = client.get("/api/transactions", headers=ALICE).json()["items"]
    assert client.post("/api/transactions/reanalyze", headers=BOB).status_code == 204
    assert client.get("/api/transactions", headers=ALICE).json()["items"] == before


def test_bob_cannot_see_or_change_alice_recurring(client):
    from datetime import date
    from app.services.recurring import add_months
    rows = [row(date=add_months(date.today(), -k).isoformat(), description_raw="NETFLIX COM", amount="649.00", reference=None)
            for k in (2, 1, 0)]
    client.post("/api/import/batch", json={"rows": rows}, headers=ALICE)
    series = client.get("/api/recurring", headers=ALICE).json()["series"]
    assert len(series) == 1
    assert client.get("/api/recurring", headers=BOB).json() == {"series": [], "monthly_committed": "0.00", "upcoming": []}
    assert client.patch(f"/api/recurring/{series[0]['id']}", json={"user_status": "dismissed"}, headers=BOB).status_code == 404
    client.post("/api/recurring/refresh", headers=BOB)
    assert client.get("/api/recurring", headers=ALICE).json()["series"] == series


def test_bob_cannot_touch_alice_budgets(client):
    budget = client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "5000"}, headers=ALICE).json()
    assert client.get("/api/budgets", headers=BOB).json()["items"] == []
    assert client.patch(f"/api/budgets/{budget['id']}", json={"monthly_limit": "1"}, headers=BOB).status_code == 404
    assert client.delete(f"/api/budgets/{budget['id']}", headers=BOB).status_code == 404
    assert client.get("/api/budgets/status", headers=BOB).json()["categories"] == []
    assert [l["category"] for l in client.get("/api/budgets/status", headers=ALICE).json()["categories"]] == ["Food & Dining"]
    # Bob's own budget for the same category is independent
    assert client.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": "100"}, headers=BOB).status_code == 201
    mine = client.get("/api/budgets", headers=ALICE).json()["items"]
    assert [(b["id"], b["monthly_limit"], b["is_active"]) for b in mine] == [(budget["id"], "5000.00", True)]


def test_first_sign_in_requests_in_parallel_make_one_user(client):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(lambda _: client.get("/api/home", headers=as_user("newbie")).status_code, range(6)))
    assert codes == [200] * 6
    assert client.get("/auth/me", headers=as_user("newbie")).json()["firebase_uid"] == "newbie"
