"""
A whole Kotak Mahindra statement imported the way the web app sends it (prod incident, 21 Oct 2026): 218 rows, 1 Jul
to 30 Sep 2026, signed in with Google. The rows were valid, but a 200-row batch made about 2,500 database round trips
and 336 commits in one request, enough on Render's free instance and Neon to pass the browser's 20-second limit. The
app then gave up, showed only "Import failed", and never resent a request that had timed out.

These rows are synthetic, shaped like what frontend/src/import (Kotak CSV, pii.js) sends for Kotak's narrations.
"""

from datetime import date, timedelta

from sqlalchemy import event

import app.core.auth as auth
from app.core.database import engine
from app.main import app
from tests.conftest import as_user, token_payload

GINA = as_user("gina")
IMPORT_ID = "3f0e7a52-1c2b-4d5e-8f90-123456789abc"
BATCH = 50                     # frontend/src/import/submit.js BATCH_SIZE
MERCHANTS = ["ZEPTO MARKETPLACE", "SWIGGY", "ZOMATO LTD", "UBER INDIA", "AMAZON PAY", "BLINKIT", "BESCOM", "AIRTEL"]
PEOPLE = ["SANJAY VERMA", "PRIYA NAIR", "AMIT SHAH"]


def kotak_rows(n=218):
    """Kotak narrations after the browser's PII pass: UPI/IMPS refs masked in the text, the UTR kept as the reference."""
    rows = []
    for i in range(n):
        day = (date(2026, 7, 1) + timedelta(days=i * 92 // n)).isoformat()
        utr = str(600000000000 + i * 7919)
        amount = f"{(i * 137) % 4000 + 49}.00"
        kind = i % 9
        if kind == 0:
            desc, ref, amount, direction = f"NEFT/ACME PAYROLL/N{100000 + i}", f"NEFT-N{100000 + i}", "85000.00", "credit"
        elif kind == 1:
            desc, ref, direction = f"UPI/{PEOPLE[i % 3]}/XXXX/split", utr, "debit"
        elif kind == 2:
            desc, ref, direction = f"IMPS/{PEOPLE[i % 3]}/XXXX", utr, "credit"
        elif kind == 3:
            desc, ref, amount, direction = f"ATM WDL/KOTAK ATM MUMBAI/{i}", f"ATM-{1000 + i}", "2000.00", "debit"
        elif kind == 4:
            desc, ref, amount, direction = "NACH/LIC OF INDIA/POLICY XXXX", f"NACH-0{i % 9}", "5230.00", "debit"
        elif kind == 5:
            desc, ref, direction = f"POS/{MERCHANTS[i % 8]}/BANGALORE", f"POS-{utr[:8]}", "debit"
        else:
            desc, ref, direction = f"UPI/{MERCHANTS[i % 8]}/XXXX/Payment", utr, "debit"
        rows.append({"date": day, "description_raw": desc, "amount": amount, "direction": direction, "reference": ref,
                     "source_type": "bank_csv", "source_label": "Kotak Mahindra Bank", "type": "transaction"})
    return rows


def google_sign_in(monkeypatch):
    """A Google sign-in: Firebase may leave email_verified unset, and Google's address counts as verified."""
    monkeypatch.setattr(auth, "verify_firebase_token", lambda token, check_revoked=False: token_payload(
        token, email_verified=False, firebase={"sign_in_provider": "google.com"}))


class Counts:
    """SQL statements and commits on the API's engine while in use."""

    def __enter__(self):
        self.statements = self.commits = 0
        event.listen(engine, "before_cursor_execute", self._statement)
        event.listen(engine, "commit", self._commit)
        return self

    def __exit__(self, *exc):
        event.remove(engine, "before_cursor_execute", self._statement)
        event.remove(engine, "commit", self._commit)

    def _statement(self, *args):
        self.statements += 1

    def _commit(self, *args):
        self.commits += 1


def send(client, rows):
    totals = {}
    for i in range(0, len(rows), BATCH):
        res = client.post("/api/import/batch", json={"rows": rows[i:i + BATCH], "import_id": IMPORT_ID}, headers=GINA)
        assert res.status_code == 200, res.text
        for k, v in res.json().items():
            totals[k] = totals.get(k, 0) + v
    return totals


def test_kotak_statement_from_a_google_account_imports_in_bounded_requests(client, monkeypatch):
    google_sign_in(monkeypatch)
    rows = kotak_rows()

    with Counts() as first:
        res = client.post("/api/import/batch", json={"rows": rows[:BATCH], "import_id": IMPORT_ID}, headers=GINA)
    assert res.status_code == 200, res.text
    assert res.json()["imported"] == BATCH and res.json()["failed"] == 0
    # The work per request is what timed out: about a commit and a dozen statements a row, not one more commit for
    # every categorised row (the model_metrics count is written once per batch)
    assert first.commits <= BATCH + 5, first.commits
    assert first.statements <= BATCH * 14, first.statements

    totals = send(client, rows[BATCH:])
    assert totals["imported"] == len(rows) - BATCH and totals["failed"] == 0
    assert client.get("/api/transactions", params={"limit": 1}, headers=GINA).json()["total"] == len(rows)


def test_resending_a_timed_out_batch_saves_nothing_twice(client, monkeypatch):
    """The web app resends a batch whose answer it never got (it may have been saved): the rows come back as duplicates."""
    google_sign_in(monkeypatch)
    rows = kotak_rows()
    assert send(client, rows)["imported"] == len(rows)
    again = send(client, rows)
    assert again["imported"] == 0 and again["duplicates_merged"] == len(rows) and again["failed"] == 0
    assert client.get("/api/transactions", params={"limit": 1}, headers=GINA).json()["total"] == len(rows)


def test_errors_the_api_makes_itself_still_reach_the_browser(client):
    """Unhandled errors (500) and oversized bodies (413) are answered outside CORSMiddleware; without CORS headers the
    browser hides them and the app can only say "Import failed"."""
    from app.core.config import settings
    origin = settings.cors_origins()[0]

    def boom():
        raise RuntimeError("boom")
    app.add_api_route("/test-boom-cors", boom, methods=["POST"])
    try:
        res = client.post("/test-boom-cors", headers={"Origin": origin})
    finally:
        app.router.routes.pop()
    assert res.status_code == 500 and res.json()["request_id"] == res.headers["x-request-id"]
    assert res.headers["access-control-allow-origin"] == origin
    assert "x-request-id" in res.headers["access-control-expose-headers"].lower()

    big = b"x" * (1024 * 1024 + 1)
    res = client.post("/api/import/batch", content=big, headers={**GINA, "Origin": origin, "content-type": "application/json"})
    assert res.status_code == 413 and res.headers["access-control-allow-origin"] == origin

    res = client.post("/api/import/batch", content=big, headers={**GINA, "Origin": "https://evil.example", "content-type": "application/json"})
    assert res.status_code == 413 and "access-control-allow-origin" not in res.headers
