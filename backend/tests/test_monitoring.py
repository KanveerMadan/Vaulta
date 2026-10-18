"""Error monitoring (app/core/monitoring.py): off without a DSN, errors only, and nothing personal leaves the server."""

import json
import logging

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from app.core import monitoring
from app.core.config import settings
from app.main import app

# planted in every place an event can pick data up from
SECRETS = ["UPI-RAHUL SHARMA", "rahul.s@okaxis", "priya@example.com", "1,234.50", "4210.50", "Swiggy Bangalore",
           "sessiontoken123", "Bearer eyJhbGciOi", "searchterm-netflix", "412345678901"]


class Recording(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.envelopes = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope.serialize().decode("utf-8", "replace"))


@pytest.fixture
def recording(monkeypatch):
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://public@sentry.example/0")
    transport = Recording()
    assert monitoring.init(transport=transport)
    yield transport
    sentry_sdk.get_client().close()
    sentry_sdk.init(dsn=None)


def test_off_without_a_dsn(monkeypatch):
    monkeypatch.setattr(settings, "SENTRY_DSN", "")
    assert monitoring.init() is False


def test_errors_only_with_no_pii_tracing_or_local_variables(recording):
    options = sentry_sdk.get_client().options
    assert options["send_default_pii"] is False and options["include_local_variables"] is False
    assert options["traces_sample_rate"] == 0 and options["max_request_body_size"] == "never"
    assert options["profiles_sample_rate"] == 0 and not options.get("enable_logs")


def test_a_real_error_reaches_sentry_without_anything_personal(recording):
    def boom(payload: dict):
        logging.getLogger("app.test").warning(f"importing {payload['rows'][0]['description_raw']} for priya@example.com")
        raise ValueError(f"bad row 'UPI-RAHUL SHARMA-rahul.s@okaxis' amount 1,234.50 at Swiggy Bangalore ref 412345678901")

    app.add_api_route("/monitoring-test-error", boom, methods=["POST"])
    try:
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post("/monitoring-test-error?q=searchterm-netflix&token=sessiontoken123",
                          json={"rows": [{"description_raw": "UPI-RAHUL SHARMA-rahul.s@okaxis", "amount": "4210.50"}]},
                          headers={"Authorization": "Bearer eyJhbGciOi", "Cookie": "session=sessiontoken123"})
        assert res.status_code == 500
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/monitoring-test-error"]
    sentry_sdk.flush()
    sent = "\n".join(recording.envelopes)
    assert "ValueError" in sent and "monitoring-test-error" in sent          # the error and its route arrive
    leaked = [s for s in SECRETS if s in sent]
    assert leaked == [], leaked


def test_scrubbing_events_and_breadcrumbs_directly():
    event = {
        "request": {"method": "POST", "url": "https://api.vaulta.in/api/import/batch?token=sessiontoken123",
                    "data": {"description_raw": "UPI-RAHUL SHARMA"}, "cookies": {"s": "sessiontoken123"},
                    "headers": {"Authorization": "Bearer eyJhbGciOi"}, "query_string": "q=searchterm-netflix"},
        "user": {"email": "priya@example.com"}, "extra": {"row": "Swiggy Bangalore"},
        "contexts": {"runtime": {"name": "CPython"}, "row": {"amount": "4210.50"}},
        "exception": {"values": [{"type": "KeyError", "value": "'rahul.s@okaxis' 1,234.50 ref 412345678901",
                                  "stacktrace": {"frames": [{"function": "f", "vars": {"x": "Swiggy Bangalore"}}]}}]},
        "logentry": {"message": "paid priya@example.com ₹4210.50", "params": ["UPI-RAHUL SHARMA"]},
        "breadcrumbs": {"values": [{"category": "httplib", "message": "GET 'Swiggy Bangalore'",
                                    "data": {"method": "GET", "url": "https://x/y?q=searchterm-netflix", "body": "4210.50"}}]},
    }
    out = json.dumps(monitoring.scrub_event(event))
    assert [s for s in SECRETS if s in out] == []
    assert '"KeyError"' in out and '"function": "f"' in out and "CPython" in out and "/api/import/batch" in out
