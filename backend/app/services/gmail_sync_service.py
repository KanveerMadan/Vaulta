"""
Gmail Sync Service — Phase 2

Fetches transaction-relevant emails ONLY (via Gmail API `q=` sender filter —
never a full mailbox scan), parses amounts/merchants from email bodies,
and inserts Transaction records.

PRIVACY COMMITMENT (see gmail_oauth_service.py header):
  Every messages.list call below includes a `q` filter restricted to known
  transactional senders. We never request or read the user's general inbox.

Email parsing rules:
  Rules are kept as a versioned list (EMAIL_PARSE_RULES) so they can be updated
  without a full redeploy if extracted to config later (Phase 2 roadmap note:
  "rules must be updatable without a full deploy if possible" — currently
  in-code but isolated to this module for easy hot-patching).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, List
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.encryption import decrypt_token, encrypt_token
from app.models.transaction import Transaction, TransactionSource
from app.models.user import User
from app.services.gmail_oauth_service import refresh_access_token, token_expiry_from_now, GmailOAuthError
from app.services.merchant_normalizer import normalize

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"

# Known transactional senders — Gmail search query syntax.
# This list IS the privacy boundary: only emails matching this query are ever fetched.
TRANSACTION_SENDER_QUERY = (
    "from:(swiggy.in OR zomato.com OR amazon.in OR flipkart.com OR irctc.co.in "
    "OR bookmyshow.com OR uber.com OR olacabs.com OR myntra.com OR ajio.com "
    "OR nykaa.com OR bigbasket.com OR blinkit.com OR zeptonow.com "
    "OR alerts.hdfcbank.net OR icicibank.com OR sbi.co.in OR axisbank.com OR kotak.com)"
    " (subject:(order OR receipt OR invoice OR payment OR transaction OR debited OR spent))"
)

# Per-sender amount extraction patterns: (sender_domain_substring, regex, group_index)
# Each regex must capture the amount as a numeric string in group 1.
EMAIL_PARSE_RULES: List[tuple] = [
    ("swiggy.in", r"(?:Total|Grand Total|Amount Paid)[:\s₹]*([\d,]+\.?\d*)", 1),
    ("zomato.com", r"(?:Total|Grand Total|Amount Paid)[:\s₹]*([\d,]+\.?\d*)", 1),
    ("amazon.in", r"(?:Order Total|Grand Total)[:\s₹]*([\d,]+\.?\d*)", 1),
    ("flipkart.com", r"(?:Order Total|Amount Paid)[:\s₹]*([\d,]+\.?\d*)", 1),
    ("irctc.co.in", r"(?:Total Fare|Amount)[:\s₹]*([\d,]+\.?\d*)", 1),
    ("bookmyshow.com", r"(?:Total Amount|Amount Paid)[:\s₹]*([\d,]+\.?\d*)", 1),
    # Generic bank debit alert pattern: "debited by Rs.1,234.56" / "INR 1,234.56 debited"
    (
        "bank",
        r"(?:debited\s*(?:by|with|for)?\s*(?:Rs\.?|INR|₹)\s*([\d,]+\.?\d*)|"
        r"(?:Rs\.?|INR|₹)\s*([\d,]+\.?\d*)\s*(?:debited|has been debited))",
        1,
    ),
    # Fallback: any ₹/Rs amount near "paid"/"total"
    ("generic", r"(?:Total|Paid|Amount)[:\s₹]*(?:Rs\.?|INR)?\s*₹?\s*([\d,]+\.?\d*)", 1),
]

BANK_SENDER_DOMAINS = {"alerts.hdfcbank.net", "icicibank.com", "sbi.co.in", "axisbank.com", "kotak.com"}


class GmailSyncError(Exception):
    """Raised on sync failures that should mark the sync as failed but not crash the worker."""
    pass


# ─────────────────────────────────────────────
# Token management
# ─────────────────────────────────────────────

async def _get_valid_access_token(db: Session, user: User) -> str:
    """
    Return a usable Gmail access token, refreshing if necessary.
    Updates user.gmail_access_token in DB if refreshed.

    Raises GmailSyncError("RECONNECT_REQUIRED") if the refresh token is invalid —
    caller must set user.gmail_connected = False and notify the user.
    """
    if not user.gmail_refresh_token:
        raise GmailSyncError("RECONNECT_REQUIRED")

    try:
        refresh_token = decrypt_token(user.gmail_refresh_token)
    except Exception as e:
        logger.error(f"Failed to decrypt refresh token for user {user.id}: {e}")
        raise GmailSyncError("RECONNECT_REQUIRED") from e

    try:
        token_data = await refresh_access_token(refresh_token)
    except GmailOAuthError as e:
        if str(e) == "REFRESH_TOKEN_INVALID":
            user.gmail_connected = False
            db.commit()
            raise GmailSyncError("RECONNECT_REQUIRED") from e
        raise GmailSyncError(f"Token refresh failed: {e}") from e

    new_access_token = token_data["access_token"]
    user.gmail_access_token = encrypt_token(new_access_token)
    db.commit()

    return new_access_token


# ─────────────────────────────────────────────
# Email fetching
# ─────────────────────────────────────────────

async def _list_message_ids(access_token: str, after_timestamp: Optional[datetime] = None) -> List[str]:
    """
    List message IDs matching TRANSACTION_SENDER_QUERY.
    If after_timestamp is given, restricts to emails received after that time
    (incremental sync).
    """
    query = TRANSACTION_SENDER_QUERY
    if after_timestamp:
        # Gmail search syntax: after:YYYY/MM/DD (date-only granularity)
        date_str = after_timestamp.strftime("%Y/%m/%d")
        query += f" after:{date_str}"

    message_ids: List[str] = []
    page_token: Optional[str] = None

    async with httpx.AsyncClient(timeout=20.0) as client:
        for _ in range(10):  # Cap pagination at 10 pages (500 messages) per sync run
            params = {"q": query, "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token

            resp = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            if resp.status_code == 401:
                raise GmailSyncError("ACCESS_TOKEN_EXPIRED")
            if resp.status_code != 200:
                logger.error(f"Gmail messages.list failed: {resp.status_code} {resp.text}")
                raise GmailSyncError(f"Gmail API error: {resp.status_code}")

            data = resp.json()
            message_ids.extend(m["id"] for m in data.get("messages", []))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    return message_ids


async def _fetch_message(access_token: str, message_id: str) -> dict:
    """Fetch full message content (headers + body) for a single message ID."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{GMAIL_API_BASE}/users/me/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "full"},
        )
    if resp.status_code == 401:
        raise GmailSyncError("ACCESS_TOKEN_EXPIRED")
    if resp.status_code != 200:
        logger.warning(f"Gmail messages.get failed for {message_id}: {resp.status_code}")
        return {}
    return resp.json()


def _decode_body(payload: dict) -> str:
    """Extract and decode the plain-text or HTML body from a Gmail message payload."""
    def _walk(part: dict) -> Optional[str]:
        mime_type = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data")
        if body_data and mime_type in ("text/plain", "text/html"):
            try:
                decoded = base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="ignore")
                return decoded
            except Exception:
                return None
        for sub in part.get("parts", []):
            result = _walk(sub)
            if result:
                return result
        return None

    return _walk(payload) or ""


def _strip_html(text: str) -> str:
    """Crude HTML tag stripper — good enough for amount extraction, not for display."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _get_header(headers: List[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


# ─────────────────────────────────────────────
# Email -> Transaction parsing
# ─────────────────────────────────────────────

def _parse_amount_str(raw: str) -> Optional[Decimal]:
    cleaned = raw.replace(",", "").strip()
    try:
        value = Decimal(cleaned)
        return value if value > 0 else None
    except InvalidOperation:
        return None


def _extract_amount(sender: str, body_text: str) -> Optional[Decimal]:
    """Try sender-specific rules first, then generic fallback."""
    sender_lower = sender.lower()

    # Sender-specific rules
    for domain, pattern, group in EMAIL_PARSE_RULES:
        if domain in ("bank", "generic"):
            continue
        if domain in sender_lower:
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                amount = _parse_amount_str(match.group(group))
                if amount:
                    return amount

    # Bank debit alert rule
    if any(bank_domain in sender_lower for bank_domain in BANK_SENDER_DOMAINS):
        for domain, pattern, _ in EMAIL_PARSE_RULES:
            if domain == "bank":
                match = re.search(pattern, body_text, re.IGNORECASE)
                if match:
                    amount_str = match.group(1) or match.group(2)
                    amount = _parse_amount_str(amount_str)
                    if amount:
                        return amount

    # Generic fallback
    for domain, pattern, group in EMAIL_PARSE_RULES:
        if domain == "generic":
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                amount = _parse_amount_str(match.group(group))
                if amount:
                    return amount

    return None


def _make_idempotency_key(user_id: uuid.UUID, message_id: str) -> str:
    """SHA256 of (user_id + gmail message_id) — Gmail message IDs are globally unique per user."""
    payload = f"gmail|{user_id}|{message_id}"
    return hashlib.sha256(payload.encode()).hexdigest()


# ─────────────────────────────────────────────
# Main sync entrypoint
# ─────────────────────────────────────────────

async def sync_gmail_for_user(db: Session, user: User, full_sync: bool = False) -> dict:
    """
    Sync transaction emails for a single user.

    Args:
        full_sync: if True, ignores `gmail_last_sync_at` and fetches all matching
                   emails (used on initial connect). Otherwise incremental.

    Returns:
        {"messages_scanned": int, "inserted": int, "skipped_duplicate": int, "skipped_unparsed": int}

    This function is called by:
      - app/workers/gmail_sync_worker.py (Celery task, scheduled every 6h)
      - app/api/routes/gmail.py (manual "Sync now" button, full_sync=True on connect)
    """
    if not user.gmail_connected:
        raise GmailSyncError("GMAIL_NOT_CONNECTED")

    access_token = await _get_valid_access_token(db, user)

    after_timestamp = None if full_sync else user.gmail_last_sync_at

    try:
        message_ids = await _list_message_ids(access_token, after_timestamp=after_timestamp)
    except GmailSyncError as e:
        if str(e) == "ACCESS_TOKEN_EXPIRED":
            # Token expired mid-call (rare race) — refresh once and retry
            access_token = await _get_valid_access_token(db, user)
            message_ids = await _list_message_ids(access_token, after_timestamp=after_timestamp)
        else:
            raise

    inserted = 0
    skipped_duplicate = 0
    skipped_unparsed = 0

    for message_id in message_ids:
        try:
            message = await _fetch_message(access_token, message_id)
        except GmailSyncError:
            access_token = await _get_valid_access_token(db, user)
            message = await _fetch_message(access_token, message_id)

        if not message:
            skipped_unparsed += 1
            continue

        headers = message.get("payload", {}).get("headers", [])
        sender = _get_header(headers, "From")
        subject = _get_header(headers, "Subject")
        date_header = _get_header(headers, "Date")

        body_raw = _decode_body(message.get("payload", {}))
        body_text = _strip_html(body_raw)

        amount = _extract_amount(sender, body_text)
        if not amount:
            skipped_unparsed += 1
            continue

        try:
            txn_date = parsedate_to_datetime(date_header)
            if txn_date.tzinfo is None:
                txn_date = txn_date.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            txn_date = datetime.now(timezone.utc)

        merchant_raw = sender or subject
        normalized = normalize(merchant_raw)

        idem_key = _make_idempotency_key(user.id, message_id)

        txn = Transaction(
            id=uuid.uuid4(),
            user_id=user.id,
            source=TransactionSource.gmail,
            merchant_raw=merchant_raw,
            merchant_clean=normalized.merchant_clean,
            category=normalized.category if normalized.confidence >= 0.5 else None,
            amount=amount,
            currency="INR",
            transaction_date=txn_date,
            idempotency_key=idem_key,
            raw_source_data={"subject": subject, "sender": sender, "message_id": message_id},
        )

        try:
            db.add(txn)
            db.flush()
            inserted += 1
        except IntegrityError:
            db.rollback()
            skipped_duplicate += 1

    user.gmail_last_sync_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        f"Gmail sync complete: user={user.id}, scanned={len(message_ids)}, "
        f"inserted={inserted}, dup={skipped_duplicate}, unparsed={skipped_unparsed}"
    )

    return {
        "messages_scanned": len(message_ids),
        "inserted": inserted,
        "skipped_duplicate": skipped_duplicate,
        "skipped_unparsed": skipped_unparsed,
    }