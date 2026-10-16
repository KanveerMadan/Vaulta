"""
Structured logs and the per-request wrapper.

Every log line is one JSON object: time, level, logger, message, and for requests the request id and a keyed hash
of the user id (user_ref). Each request also logs one `request` line: method, route template (never the raw path or
query string, which can carry tokens), status and latency. Never logged: amounts, merchant names, narrations,
email addresses, tokens, raw user ids. A last-resort filter masks email addresses and bearer tokens in messages.
tests/test_logs.py captures the logs of a full account's activity and checks for all of these.

RequestMiddleware (pure ASGI, outermost) per request:
  - a request id (X-Request-ID on the response, in every log line and in error bodies)
  - a fresh user scope (app/core/scope.py)
  - security headers on every response
  - MAX_BODY_BYTES on request bodies (413)
  - unhandled errors → 500 {"detail": "Something went wrong.", "request_id"}: no stack trace or message to the client;
    the log gets the exception type and where it was raised, not its message (which can hold SQL parameters)
"""

from __future__ import annotations

import json
import logging
import re
import time
import traceback
import uuid
from contextvars import ContextVar
from typing import Optional

from app.core.config import settings

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

MAX_BODY_BYTES = 1024 * 1024          # imports are ≤ 500 rows; inbound email has its own 256 KB cap

API_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-XSS-Protection": "0",
}
HSTS = "max-age=63072000; includeSubDomains; preload"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_BEARER = re.compile(r"(?i)bearer\s+\S+")


def user_ref(user_id) -> Optional[str]:
    """A stable, keyed reference to a user for logs: correlates lines without revealing the id."""
    if user_id is None:
        return None
    from app.core.crypto import lookup_hash
    return lookup_hash("log", str(user_id))[:16]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        from app.core.scope import current_user_id
        msg = _BEARER.sub("Bearer [redacted]", _EMAIL.sub("[email]", record.getMessage()))
        out = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname, "logger": record.name, "msg": msg}
        if rid := request_id_var.get():
            out["request_id"] = rid
        if uid := current_user_id():
            out["user"] = user_ref(uid)
        for key in ("method", "route", "status", "latency_ms"):
            if hasattr(record, key):
                out[key] = getattr(record, key)
        if record.exc_info:
            out["error"] = record.exc_info[0].__name__
        return json.dumps(out, ensure_ascii=False)


def configure() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    for noisy in ("uvicorn.access",):        # its lines carry raw paths and query strings
        logging.getLogger(noisy).disabled = True


access = logging.getLogger("vaulta.request")


def _where(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)
    app_frames = [f for f in frames if "/app/" in f.filename] or frames
    f = app_frames[-1] if app_frames else None
    return f"{f.filename.rsplit('/app/', 1)[-1]}:{f.lineno}" if f else "?"


class RequestMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from app.core.scope import request_scope
        rid = uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        state = {"status": 500, "started": False}

        headers = dict((k.decode().lower(), v.decode()) for k, v in scope.get("headers", []))
        length = headers.get("content-length")

        too_large = json.dumps({"detail": "Request too large.", "request_id": rid}).encode()

        async def send_wrapper(message):
            if state.get("too_large"):          # the body went over the limit mid-stream: answer 413 instead
                if message["type"] == "http.response.start":
                    message = {"type": "http.response.start", "status": 413,
                               "headers": [(b"content-type", b"application/json")]}
                elif message["type"] == "http.response.body":
                    message = {"type": "http.response.body", "body": too_large if not state.get("sent_413") else b""}
                    state["sent_413"] = True
            if message["type"] == "http.response.start":
                state["started"] = True
                state["status"] = message["status"]
                extra = [(k.encode(), v.encode()) for k, v in API_HEADERS.items()]
                if settings.ENVIRONMENT == "production":
                    extra.append((b"strict-transport-security", HSTS.encode()))
                extra.append((b"x-request-id", rid.encode()))
                present = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [(k, v) for k, v in extra if k not in present]
            await send(message)

        received = 0

        async def receive_wrapper():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_BODY_BYTES:
                    state["too_large"] = True     # stop reading; the app sees an empty, finished body
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def reply(status: int, body: dict):
            await send_wrapper({"type": "http.response.start", "status": status,
                                "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": json.dumps(body).encode()})

        with request_scope():
            try:
                if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
                    await reply(413, {"detail": "Request too large.", "request_id": rid})
                else:
                    await self.app(scope, receive_wrapper, send_wrapper)
            except Exception as exc:
                logging.getLogger("vaulta.error").error(f"unhandled {exc.__class__.__name__} at {_where(exc)}")
                if not state["started"]:
                    await reply(500, {"detail": "Something went wrong.", "request_id": rid})
            finally:
                route = scope.get("route")
                access.info("request", extra={
                    "method": scope.get("method"), "route": getattr(route, "path", None) or "unmatched",
                    "status": state["status"], "latency_ms": round((time.perf_counter() - started) * 1000)})
                request_id_var.reset(token)
