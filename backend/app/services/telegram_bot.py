"""
The Telegram bot. One update in, replies out (services/telegram.py).

- Unlinked chats get only "link your account" (or the link itself, /start <code>).
- Free text that parses as an expense (services/quick_add.py) becomes a
  pending entry with [✓ Save] [✎ Edit category] [✗ Cancel]; nothing is saved
  without ✓. Anything else goes to the chat assistant (same tools, AI toggle
  and confirmation tokens), whose actions are confirmed with buttons.
- Commands: /today /week /safe /undo /unlink /help.
- Photos are not processed: the reply points to the web capture.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.models.telegram import TelegramEntry, TelegramLinkCode
from app.models.user import User
from app.schemas.transaction import CATEGORIES, ManualTransactionCreate
from app.services import analytics, chat, telegram, transaction_service
from app.services.chat_tools import inr
from app.services.quick_add import parse_quick_add

logger = logging.getLogger(__name__)

LINK_CODE_TTL = timedelta(minutes=10)
LINK_CODE_LENGTH = 8
LINK_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I
UNDO_WINDOW = timedelta(minutes=10)
RATE_LIMIT = 20             # messages per chat
RATE_WINDOW_SECONDS = 60
CATEGORY_CHOICES = sorted(c for c in CATEGORIES if c not in ("Sent to People", "Received from People", "Transfers"))

LINK_FIRST = ("This chat isn't linked to a Vaulta account yet. In Vaulta, open Settings → Link Telegram, "
              "then send /start followed by the code shown there.")
HELP = ("Send an expense like \"150 auto cash\" or \"1.2k groceries yesterday\" and tap ✓ Save.\n"
        "Ask anything, e.g. \"how much on food this month?\"\n"
        "/today · /week · /safe · /undo · /unlink")
PHOTO = ("I don't read photos here, so your bill stays private. Use Scan bill on the Vaulta dashboard: "
         "the photo is read on your phone and never uploaded.")

# ponytail: per-process limiter; with several API instances each allows RATE_LIMIT. Move to the DB if that matters.
_recent: dict[int, deque] = defaultdict(deque)


def rate_limited(chat_id: int) -> bool:
    now = time.monotonic()
    q = _recent[chat_id]
    while q and now - q[0] > RATE_WINDOW_SECONDS:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


# ── Linking ───────────────────────────────────────────────────────────────────

def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def new_link_code(db: Session, user: User) -> tuple[str, datetime]:
    """A fresh single-use code; any earlier unused code for the user stops working."""
    db.query(TelegramLinkCode).filter(TelegramLinkCode.user_id == user.id, TelegramLinkCode.used_at.is_(None)).delete()
    code = "".join(secrets.choice(LINK_CODE_ALPHABET) for _ in range(LINK_CODE_LENGTH))
    expires = clock.now() + LINK_CODE_TTL
    db.add(TelegramLinkCode(user_id=user.id, code_hash=_hash(code), expires_at=expires))
    db.commit()
    return code, expires


def redeem(db: Session, code: str, chat_id: int) -> Optional[User]:
    row = db.query(TelegramLinkCode).filter(TelegramLinkCode.code_hash == _hash(code)).first()
    if row is None or row.used_at is not None or row.expires_at < clock.now():
        return None
    row.used_at = clock.now()
    db.query(User).filter(User.telegram_chat_id == chat_id).update({"telegram_chat_id": None})   # one account per chat
    user = db.query(User).filter(User.id == row.user_id).one()
    user.telegram_chat_id = chat_id
    db.commit()
    return user


def unlink(db: Session, user: User) -> None:
    user.telegram_chat_id = None
    db.commit()


# ── Replies ───────────────────────────────────────────────────────────────────

def _local_today(user: User):
    return clock.now().astimezone(clock.zone(user.timezone)).date()


def _entry_text(p: dict) -> str:
    day = "today" if p["date"] == p.get("today") else p["date"]
    sign = "+" if p["direction"] == "credit" else ""
    return f"{sign}{inr(Decimal(p['amount']))} · {p['merchant']} · {p['category'] or 'no category'} · {day} · {p['payment_method']}"


def _entry_buttons(entry_id) -> list:
    return [[("✓ Save", f"save:{entry_id}"), ("✎ Edit category", f"cat:{entry_id}"), ("✗ Cancel", f"cancel:{entry_id}")]]


def _today(db: Session, user: User) -> str:
    day = _local_today(user)
    s = analytics.spend_summary(db, user.id, day, day, "merchant")
    lines = [f"Today: {inr(s['total'])} spent"] + [f"  {g['label']} {inr(g['total'])}" for g in s["groups"][:5]]
    return "\n".join(lines)


def _week(db: Session, user: User) -> str:
    day = _local_today(user)
    week = analytics.spend_summary(db, user.id, day - timedelta(days=day.weekday()), day)["total"]
    b = analytics.budget_status(db, user.id, day)
    text = f"This week: {inr(week)} spent.\nThis month: {inr(b['total_spend'])}"
    if b["overall"]:
        text += f" of {inr(b['overall']['limit'])} budget ({b['overall']['pct']}%)"
    over = [c for c in b["categories"] if c["over"]]
    if over:
        text += "\nOver budget: " + ", ".join(f"{c['category']} by {inr(-c['remaining'])}" for c in over)
    return text + "."


def _safe(db: Session, user: User) -> str:
    s = analytics.safe_to_spend_today(db, user.id)
    if s["amount"] is None:
        return "Set a budget in Vaulta (or import this month's income) and I can tell you what's safe to spend."
    return f"Safe to spend today: {inr(s['amount'])} (from your {s['basis']}, {s['days_left_including_today']} days left this month)."


def _undo(db: Session, user: User) -> str:
    entry = (db.query(TelegramEntry).filter(TelegramEntry.user_id == user.id, TelegramEntry.status == "saved")
             .order_by(TelegramEntry.saved_at.desc()).first())
    if entry is None or clock.now() - entry.saved_at > UNDO_WINDOW:
        return "Nothing to undo: /undo works for 10 minutes after saving."
    txn = transaction_service.get_owned_transaction(db, user, entry.transaction_id)
    if txn is not None:
        if not transaction_service.is_manual_only(txn):
            return "That entry has since matched a bank transaction, so I left it. Change it in the app instead."
        transaction_service.delete_manual_transaction(db, txn)
    entry.status = "undone"
    db.commit()
    return f"Removed: {_entry_text(entry.payload)}"


def _ask_assistant(db: Session, user: User, chat_id: int, text: str) -> None:
    if not user.ai_chat_enabled:
        telegram.send(chat_id, "AI chat is turned off in Vaulta's Settings, so I can only log expenses.")
        return
    try:
        result = chat.handle_message(db, user, text, uuid.uuid5(uuid.NAMESPACE_URL, f"telegram:{user.id}"))
    except chat.ChatLimit as e:
        telegram.send(chat_id, str(e))
        return
    lines = [result["reply"]]
    for t in result["tables"]:
        lines += ["", t["title"]] + ["  " + " · ".join(str(c) for c in row) for row in t["rows"]]
    telegram.send(chat_id, "\n".join(lines))
    for a in result["actions"]:
        telegram.send(chat_id, a["summary"], [[("✓ Confirm", f"ok:{a['token']}"), ("✗ Cancel", f"no:{a['token']}")]])


def _message(db: Session, chat_id: int, msg: dict) -> None:
    text = (msg.get("text") or "").strip()
    if text.startswith("/start"):
        code = text[len("/start"):].strip()
        user = redeem(db, code, chat_id) if code else None
        telegram.send(chat_id, f"Linked to Vaulta. {HELP}" if user else (LINK_FIRST if code == "" else
                      "That code is wrong or has expired. Get a new one in Vaulta → Settings → Link Telegram."))
        return
    user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if user is None:
        telegram.send(chat_id, LINK_FIRST)
        return
    if msg.get("photo") or msg.get("document"):
        telegram.send(chat_id, PHOTO)
        return
    command = text.split()[0].split("@")[0].lower() if text.startswith("/") else None
    if command == "/unlink":
        unlink(db, user)
        telegram.send(chat_id, "Unlinked. This chat no longer reaches your Vaulta account.")
    elif command == "/today":
        telegram.send(chat_id, _today(db, user))
    elif command == "/week":
        telegram.send(chat_id, _week(db, user))
    elif command == "/safe":
        telegram.send(chat_id, _safe(db, user))
    elif command == "/undo":
        telegram.send(chat_id, _undo(db, user))
    elif command:
        telegram.send(chat_id, HELP)
    elif text:
        parsed = None if text.endswith("?") else parse_quick_add(text, _local_today(user))
        if parsed:
            payload = {**parsed, "today": _local_today(user).isoformat()}
            entry = TelegramEntry(user_id=user.id, chat_id=chat_id, payload=payload)
            db.add(entry)
            db.commit()
            telegram.send(chat_id, _entry_text(payload), _entry_buttons(entry.id))
        else:
            _ask_assistant(db, user, chat_id, text)


def _callback(db: Session, cb: dict) -> None:
    chat_id = cb["message"]["chat"]["id"]
    message_id = cb["message"]["message_id"]
    telegram.answer_callback(cb["id"])
    user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if user is None:
        telegram.send(chat_id, LINK_FIRST)
        return
    action, _, rest = (cb.get("data") or "").partition(":")

    if action in ("ok", "no"):
        if not user.ai_chat_enabled:
            telegram.edit(chat_id, message_id, "AI chat is turned off in Vaulta's Settings.")
            return
        try:
            result = chat.resolve_action(db, user, rest, confirm=action == "ok")
        except chat.ActionUnavailable as e:
            telegram.edit(chat_id, message_id, str(e))
            return
        telegram.edit(chat_id, message_id, result["message"])
        return

    entry_id, _, extra = rest.partition(":")
    try:
        entry = db.query(TelegramEntry).filter(TelegramEntry.id == uuid.UUID(entry_id), TelegramEntry.user_id == user.id).first()
    except ValueError:
        entry = None
    if entry is None or entry.status != "pending":
        telegram.edit(chat_id, message_id, "That entry is no longer open.")
        return
    p = dict(entry.payload)
    if action == "save":
        txn = transaction_service.create_manual_transaction(db, user, ManualTransactionCreate(
            client_id=str(entry.id), date=p["date"], amount=p["amount"], direction=p["direction"],
            merchant=p["merchant"][:100], category=p["category"], payment_method=p["payment_method"]))
        entry.status, entry.transaction_id, entry.saved_at = "saved", txn.id, clock.now()
        db.commit()
        telegram.edit(chat_id, message_id, f"Saved ✓ {_entry_text(p)}\n/undo within 10 minutes to remove it.")
    elif action == "cancel":
        entry.status = "cancelled"
        db.commit()
        telegram.edit(chat_id, message_id, "Cancelled. Nothing was saved.")
    elif action == "cat":
        rows = [[(c, f"set:{entry.id}:{i}") for i, c in list(enumerate(CATEGORY_CHOICES))[j:j + 2]]
                for j in range(0, len(CATEGORY_CHOICES), 2)]
        telegram.edit(chat_id, message_id, f"{_entry_text(p)}\nPick a category:", rows)
    elif action == "set" and extra.isdigit() and int(extra) < len(CATEGORY_CHOICES):
        p["category"] = CATEGORY_CHOICES[int(extra)]
        entry.payload = p
        db.commit()
        telegram.edit(chat_id, message_id, _entry_text(p), _entry_buttons(entry.id))


def handle_update(db: Session, update: dict) -> None:
    """Process one Telegram update. Errors are logged, never raised to Telegram."""
    msg, cb = update.get("message"), update.get("callback_query")
    chat_id = (msg or {}).get("chat", {}).get("id") or (cb or {}).get("message", {}).get("chat", {}).get("id")
    if chat_id is None:
        return
    if (msg or {}).get("chat", {}).get("type", "private") != "private":
        return   # the bot only works in a private chat with the account holder
    if rate_limited(chat_id):
        return
    try:
        if cb:
            _callback(db, cb)
        elif msg:
            _message(db, chat_id, msg)
    except telegram.TelegramError as e:
        logger.warning(f"telegram: reply failed chat={chat_id}: {e}")


def send_weekly_summary(db: Session, user: User, report) -> bool:
    """Weekly report summary to the linked chat, once per report."""
    if not (user.telegram_chat_id and user.telegram_weekly and telegram.configured()) or report.telegram_sent_at:
        return False
    link = f"{settings.APP_BASE_URL.rstrip('/')}/reports/{report.id}"
    telegram.send(user.telegram_chat_id, f"{report.json['period']['label']}\n{report.narrative}\n\nFull report: {link}")
    report.telegram_sent_at = clock.now()
    db.commit()
    return True
