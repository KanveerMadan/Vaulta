"""Forwarding addresses and the inbound-email pipeline (metadata in, normalized row out)."""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime
from typing import Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.core.demo import is_demo
from app.core.crypto import lookup_hash
from app.core.scope import find_user
from app.models.inbound import GmailConfirmation, InboundEvent
from app.models.user import User
from app.schemas.imports import ImportRow
from app.services import email_alerts
from app.services.transaction_service import import_rows
from app.core.logs import user_ref

logger = logging.getLogger(__name__)

TOKEN_LENGTH = 10
TOKEN_ALPHABET = string.ascii_lowercase + string.digits   # email local parts are case-insensitive in practice
MAX_EMAIL_BYTES = 256 * 1024


def _hash(token: str) -> str:
    return lookup_hash("inbound", token.lower())


def inbound_host() -> Optional[str]:
    return f"in.{settings.INBOUND_DOMAIN.strip().lower()}" if settings.INBOUND_DOMAIN.strip() else None


def regenerate_address(db: Session, user: User) -> str:
    token = "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))
    user.inbound_token_hash = _hash(token)
    user.inbound_token_encrypted = token     # encrypted with the user's data key (models/user.py)
    db.commit()
    return token


def address_for(db: Session, user: User) -> Optional[str]:
    host = inbound_host()
    if host is None or is_demo(user):      # nobody can mail data into the shared demo
        return None
    token = user.inbound_token_encrypted or regenerate_address(db, user)
    return f"{token}@{host}"


def user_for_recipient(db: Session, recipients: str) -> Optional[User]:
    """The user whose forwarding address is among `recipients` (a To header or address)."""
    host = inbound_host()
    if host is None:
        return None
    for part in (recipients or "").split(","):
        address = email_alerts.address_of(part)
        local, _, domain = address.partition("@")
        if domain == host and len(local) == TOKEN_LENGTH:
            user = find_user(db, "inbound_token_hash", _hash(local))
            if user:
                return user
    return None


def _event(db: Session, user: User, outcome: str, bank: Optional[dict]) -> None:
    db.add(InboundEvent(user_id=user.id, outcome=outcome, bank_key=bank["key"] if bank else None,
                        bank_name=bank["name"] if bank else None))
    db.commit()


def process(db: Session, to: str, from_: str, subject: str, text: Optional[str], html: Optional[str],
            auth_results: str, received_at: Optional[datetime] = None) -> str:
    """
    Handle one email in memory. Returns the outcome. Only metadata, Gmail's
    confirmation link/code, or the normalized row (via import_rows) is stored.
    """
    user = user_for_recipient(db, to)
    if user is None:
        return "unknown_recipient"
    body = email_alerts.body_text(text, html)

    confirmation = email_alerts.gmail_confirmation(from_, subject, body, auth_results)
    if confirmation:
        db.add(GmailConfirmation(user_id=user.id, link=confirmation["link"], code=confirmation["code"]))
        _event(db, user, "gmail_confirmation", None)
        return "gmail_confirmation"

    outcome, row, bank = read_alert(user, from_, subject, body, auth_results, received_at)
    if row is None:
        if outcome in ("untrusted_sender", "auth_failed"):
            logger.info(f"inbound: discarded user={user_ref(user.id)} outcome={outcome} sender_domain={email_alerts.address_of(from_).rpartition('@')[2]}")
        _event(db, user, outcome, bank)
        return outcome
    import_rows(db, user, [row])
    _event(db, user, "parsed", bank)
    logger.info(f"inbound: parsed user={user_ref(user.id)} bank={bank['key']}")
    return "parsed"


def read_alert(user: User, from_: str, subject: str, body: str, auth_results: str,
               received_at: Optional[datetime] = None) -> tuple[str, Optional[ImportRow], Optional[dict]]:
    """
    The sender check and the parse, in memory, with nothing stored: (outcome, row or None, bank). process() stores
    the row; the bank-alert simulation (services/simulations.py) runs the same steps on a sample email.
    """
    trust = email_alerts.check_sender(from_, auth_results)
    if trust.reason != "ok":
        return ("untrusted_sender" if trust.reason == "unknown_sender" else "auth_failed"), None, trust.bank
    parsed = email_alerts.parse_alert(trust.bank, subject, body, received_at or clock.now(), holder_name=user.full_name)
    if parsed.row is None:
        return parsed.outcome, None, trust.bank
    try:
        return "parsed", ImportRow(**parsed.row), trust.bank
    except ValidationError:
        return "unparsed", None, trust.bank
