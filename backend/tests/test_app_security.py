"""Security headers, CORS, request ids, generic errors, body limits (app/core/logs.py, app/main.py)."""

import pytest
from fastapi.middleware.cors import CORSMiddleware

from app.core import logs
from app.core.config import settings
from app.main import app
from tests.conftest import as_user

USER = as_user("alice")


def test_every_response_has_the_security_headers(client):
    for res in (client.get("/health"), client.get("/api/transactions", headers=USER), client.get("/api/transactions"),
                client.get("/nope"), client.get("/unsubscribe?token=x")):
        for name, value in logs.API_HEADERS.items():
            assert res.headers[name] == value, (res.url, name)
        assert len(res.headers["x-request-id"]) == 16
    csp = logs.API_HEADERS["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp and "script-src" not in csp and "default-src 'none'" in csp


def test_hsts_in_production(client, monkeypatch):
    assert "strict-transport-security" not in client.get("/health").headers
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert client.get("/health").headers["strict-transport-security"] == logs.HSTS


def test_unhandled_errors_are_generic_with_a_request_id(client, caplog):
    def boom():
        raise RuntimeError("secret merchant SWIGGY 4500.00 in the message")
    app.add_api_route("/test-boom", boom)
    try:
        res = client.get("/test-boom")
    finally:
        app.router.routes.pop()
    assert res.status_code == 500
    body = res.json()
    assert body == {"detail": "Something went wrong.", "request_id": res.headers["x-request-id"]}
    assert "Traceback" not in res.text and "SWIGGY" not in res.text
    assert "SWIGGY" not in caplog.text and "RuntimeError" in caplog.text
    for name in logs.API_HEADERS:
        assert name in res.headers


def test_bodies_over_the_limit_are_refused(client):
    big = b"x" * (logs.MAX_BODY_BYTES + 1)
    res = client.post("/api/import/batch", content=big, headers={**USER, "content-type": "application/json"})
    assert res.status_code == 413 and res.json()["detail"] == "Request too large."

    def chunks():
        for _ in range(3):
            yield b"x" * (logs.MAX_BODY_BYTES // 2)
    res = client.post("/api/import/batch", content=chunks(), headers={**USER, "content-type": "application/json"})
    assert res.status_code == 413


def _cors():
    return next(m for m in app.user_middleware if m.cls is CORSMiddleware).kwargs


def test_cors_allows_only_configured_origins(client):
    kw = _cors()
    assert kw["allow_credentials"] is False and "*" not in kw["allow_origins"]
    ok = client.options("/api/transactions", headers={"Origin": settings.cors_origins()[0], "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == settings.cors_origins()[0]
    bad = client.options("/api/transactions", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
    preview = "https://vaulta-git-feature-x-preview.example"                     # BACKEND_CORS_ORIGIN_REGEX (conftest)
    res = client.options("/api/transactions", headers={"Origin": preview, "Access-Control-Request-Method": "GET"})
    assert res.headers.get("access-control-allow-origin") == preview
    near = client.options("/api/transactions", headers={"Origin": preview + ".evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in near.headers


@pytest.mark.parametrize("field,value", [("message", "x" * 2001)])
def test_chat_input_is_bounded(client, field, value):
    assert client.post("/api/chat", json={field: value}, headers=USER).status_code == 422
