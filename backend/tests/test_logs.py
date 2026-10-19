"""
Structured logs (app/core/logs.py): a full account's activity through the API, with every log line captured as it
would be written in production (JSON), must not contain amounts, merchant names, narrations, email addresses,
tokens or raw user ids.
"""

import io
import json
import logging

from sqlalchemy import text

from app.core import logs
from app.core.config import settings
from tests.conftest import owner_engine
from tests.test_chat import call, fake, say  # noqa: F401 (fixture)
from tests.test_end_to_end import USER, frozen_today, load_three_months  # noqa: F401 (fixture)
from tests.test_inbound import HDFC, HDFC_DKIM, UPI_DEBIT

SECRET = "x" * 40
NEVER = [
    # amounts and narrations from the fixture
    "80000", "20000.00", "1500.00", "₹", "Rs.450", "NEFT CR-ACME CORP PAYROLL", "UPI-RAVI KUMAR", "BESCOM BILL",
    "ANKIT JAIN", "R***@okaxis", "swiggy@icici", "Dear Customer",
    # merchants and people as stored
    "Swiggy", "SWIGGY", "Zepto", "ZEPTO", "Netflix", "NETFLIX", "Ravi Kumar", "Priya", "PRIYA",
    # email addresses, tokens, chat text
    "@test.local", "hdfcbank.net>", "Bearer", "rahul", "how much on biryani", "Biryani",
]


def test_logs_carry_no_personal_or_financial_data(client, fake, monkeypatch):
    out = io.StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(logs.JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    level = root.level
    root.setLevel(logging.DEBUG)
    try:
        monkeypatch.setattr(settings, "INTERNAL_SECRET", SECRET)
        monkeypatch.setattr(settings, "INBOUND_DOMAIN", "example.in")
        load_three_months(client)
        fake(call("spend_summary", start="2024-06-01", end="2024-06-30", group_by="merchant"), say("Biryani is fine."))
        client.post("/api/chat", json={"message": "how much on biryani?"}, headers=USER)
        to = client.get("/api/inbound", headers=USER).json()["address"]
        client.post("/internal/inbound-email", headers={"X-Internal-Secret": SECRET},
                    json={"to": to, "from": HDFC, "subject": "UPI txn", "text": UPI_DEBIT, "html": None, "auth_results": HDFC_DKIM})
        client.post("/api/reports/generate", json={"period_type": "monthly", "date": "2024-05-31"}, headers=USER)
        client.post("/internal/run-reports", headers={"X-Internal-Secret": SECRET})
        client.get("/api/export", headers=USER)
        client.get("/unsubscribe?token=abc.def")
        client.get("/api/transactions", headers={"Authorization": "Bearer forged-token-value"})
        client.delete("/auth/me", headers=USER)
    finally:
        root.removeHandler(handler)
        root.setLevel(level)

    lines = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
    requests = [l for l in lines if l["logger"] == "vaulta.request"]
    assert len(requests) >= 15
    assert {"request_id", "method", "route", "status", "latency_ms"} <= set(requests[0])
    assert any(r.get("user") for r in requests)                                       # a keyed reference…
    assert any(r["route"] == "/api/transactions/{transaction_id}" or r["route"] == "/api/transactions" for r in requests)
    assert not any("?" in r["route"] or "abc.def" in r["route"] for r in requests)   # never the query string

    dump = out.getvalue()
    with owner_engine.connect() as conn:                                              # …never the raw id
        ids = [str(u) for (u,) in conn.execute(text("SELECT id FROM users"))]
    found = [s for s in NEVER + ids if s in dump]
    assert found == [], f"in the logs: {found}"
    assert "forged-token-value" not in dump
