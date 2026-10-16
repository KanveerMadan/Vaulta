"""
Whose data this unit of work is about.

bind_user(db, user) makes `user` the current user, for two things at once:
  - Postgres row-level security: every transaction of the session runs `set_config('app.user_id', <id>, true)`
    (alembic a7c3e9f1d2b4), so the database itself returns and accepts only that user's rows;
  - field encryption (app/core/crypto.py): their data key is unwrapped and every Encrypted column uses it.
It is called by get_current_user for each request
and, in internal jobs (reports, alerts, demo reset, inbound email, Telegram), once per user before touching their
data. RequestMiddleware (app/core/logs.py) gives each request its own scope; outside a request (scripts, tests) the first bind creates one.

FastAPI runs sync dependencies and endpoints in separate threadpool calls, each with a copy of the request's
context, so the scope is a mutable object set once per request by the middleware rather than a value set by the
dependency (which the endpoint would not see).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

from sqlalchemy import event, text
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


_SET_USER = text("SELECT set_config('app.user_id', :u, true)")


def _set_rls_user(db: Session, user_id: Optional[uuid.UUID]) -> None:
    db.info["user_id"] = user_id
    db.execute(_SET_USER, {"u": str(user_id) if user_id else ""})


@event.listens_for(Session, "after_begin")
def _apply_rls_user(session, transaction, connection):
    """SET LOCAL lasts one transaction; re-apply the bound user at the start of every one (after each commit)."""
    user_id = session.info.get("user_id")
    connection.execute(_SET_USER, {"u": str(user_id) if user_id else ""})


def bind_user(db: Session, user) -> None:
    """Make `user` the current user. Creates their data key on first use (saved with the session's next commit)."""
    if user.id is None:
        user.id = uuid.uuid4()
    _set_rls_user(db, user.id)
    if not user.data_key:
        user.data_key = wrap(new_data_key(), user.id)
    scope = _current()
    scope.user_id = user.id
    scope.cipher = UserCipher(user.id, unwrap(user.data_key, user.id))


def unbind(db: Optional[Session] = None) -> None:
    scope = _scope.get()
    if scope is not None:
        scope.user_id = scope.cipher = None
    if db is not None:
        db.info["user_id"] = None
        tx = db.get_transaction()
        if tx is not None and tx.is_active:
            db.execute(_SET_USER, {"u": ""})


def current_user_id() -> Optional[uuid.UUID]:
    scope = _scope.get()
    return scope.user_id if scope else None


def current_cipher() -> UserCipher:
    scope = _scope.get()
    if scope is None or scope.cipher is None:
        raise CryptoError("no user is bound: call bind_user before reading or writing encrypted fields")
    return scope.cipher


@contextmanager
def request_scope():
    """A fresh, empty scope for one request (app/core/logs.py RequestMiddleware wraps every request in it)."""
    token = _scope.set(_Scope())
    try:
        yield
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
# Row-level security hides every user until one is bound, so lookups go through SECURITY DEFINER functions that
# return an id only (alembic a7c3e9f1d2b4); the row itself is then read as that user.

LOOKUP_FIELDS = ("id", "firebase_uid", "inbound_token_hash", "telegram_chat_id", "razorpay_subscription_id", "email")


def find_user(db: Session, field: str, value):
    """The user whose `field` equals `value`, bound as the current user; None if there is none."""
    from app.models.user import User
    if field not in LOOKUP_FIELDS:
        raise ValueError(f"find_user: unknown field {field}")
    if field == "id":
        user_id = value
    else:
        user_id = db.execute(text("SELECT vaulta_find_user(:f, :v)"), {"f": field, "v": str(value)}).scalar()
    if user_id is None:
        return None
    user_id = uuid.UUID(str(user_id))
    _set_rls_user(db, user_id)
    user = db.get(User, user_id, populate_existing=True)
    if user is None:
        _set_rls_user(db, current_user_id())
        return None
    bind_user(db, user)
    return user


def all_user_ids(db: Session) -> list[uuid.UUID]:
    """Every user's id, oldest first (internal jobs, which then bind each user in turn)."""
    return [uuid.UUID(str(uid)) for (uid,) in db.execute(text("SELECT vaulta_user_ids()"))]
