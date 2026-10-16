"""
Whose data this unit of work is about.

bind_user(db, user) makes `user` the current user for field encryption (app/core/crypto.py): their data key is
unwrapped and every Encrypted column read or written uses it. It is called by get_current_user for each request
and, in internal jobs (reports, alerts, demo reset, inbound email, Telegram), once per user before touching their
data. ScopeMiddleware gives each request its own scope; outside a request (scripts, tests) the first bind creates one.

FastAPI runs sync dependencies and endpoints in separate threadpool calls, each with a copy of the request's
context, so the scope is a mutable object set once per request by the middleware rather than a value set by the
dependency (which the endpoint would not see).
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.crypto import CryptoError, UserCipher, new_data_key, unwrap, wrap


class _Scope:
    __slots__ = ("user_id", "cipher")

    def __init__(self):
        self.user_id: Optional[uuid.UUID] = None
        self.cipher: Optional[UserCipher] = None


_scope: ContextVar[Optional[_Scope]] = ContextVar("vaulta_scope", default=None)


def _current() -> _Scope:
    scope = _scope.get()
    if scope is None:
        scope = _Scope()
        _scope.set(scope)
    return scope


def bind_user(db: Session, user) -> None:
    """Make `user` the current user. Creates their data key on first use (saved with the session's next commit)."""
    if user.id is None:
        user.id = uuid.uuid4()
    if not user.data_key:
        user.data_key = wrap(new_data_key(), user.id)
    scope = _current()
    scope.user_id = user.id
    scope.cipher = UserCipher(user.id, unwrap(user.data_key, user.id))
    db.info["user_id"] = user.id


def unbind(db: Optional[Session] = None) -> None:
    scope = _scope.get()
    if scope is not None:
        scope.user_id = scope.cipher = None
    if db is not None:
        db.info.pop("user_id", None)


def current_user_id() -> Optional[uuid.UUID]:
    scope = _scope.get()
    return scope.user_id if scope else None


def current_cipher() -> UserCipher:
    scope = _scope.get()
    if scope is None or scope.cipher is None:
        raise CryptoError("no user is bound: call bind_user before reading or writing encrypted fields")
    return scope.cipher


class ScopeMiddleware:
    """A fresh, empty scope for every request (pure ASGI, so it wraps the whole request including dependencies)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token = _scope.set(_Scope())
        try:
            await self.app(scope, receive, send)
        finally:
            _scope.reset(token)


@event.listens_for(Session, "before_flush")
def _one_user_per_flush(session, flush_context, instances):
    """Refuse to write a row for any user but the bound one (it would be encrypted with the wrong key)."""
    bound = current_user_id()
    if bound is None:
        return
    for obj in list(session.new) + list(session.dirty):
        owner = obj.id if obj.__class__.__name__ == "User" else getattr(obj, "user_id", None)
        if owner is not None and owner != bound:
            raise CryptoError(f"{obj.__class__.__name__} for another user written while {bound} is bound")


# ── Finding a user before anyone is bound ─────────────────────────────────────

LOOKUP_FIELDS = ("id", "firebase_uid", "inbound_token_hash", "telegram_chat_id", "razorpay_subscription_id")


def find_user(db: Session, field: str, value):
    """The user whose `field` equals `value`, bound as the current user; None if there is none."""
    from app.models.user import User
    assert field in LOOKUP_FIELDS, field
    user = db.query(User).filter(getattr(User, field) == value).first()
    if user is not None:
        bind_user(db, user)
    return user


def all_user_ids(db: Session) -> list[uuid.UUID]:
    """Every user's id, oldest first (internal jobs, which then bind each user in turn)."""
    from app.models.user import User
    return [uid for (uid,) in db.query(User.id).order_by(User.created_at)]
