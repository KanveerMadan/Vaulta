"""
Chat agent: the model answers from tool results only (services/chat_tools.py)
and can propose actions the user confirms separately.

Limits (listed in the Phase 3 report): 5 tool rounds per message, 45 s per
message, 10 messages/minute and 200/day per user, last 10 turns as context,
history purged after 30 days.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import clock, ratelimit
from app.core.demo import is_demo
from app.models.chat import ChatAction, ChatMessage
from app.models.user import User
from app.services import llm
from app.services.chat_tools import ACTION_TOOLS, READ_TOOLS, TOOL_SCHEMAS, ToolError, execute, llm_safe, propose, table_for
from app.core.logs import user_ref

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
DEADLINE_SECONDS = 45
HISTORY_TURNS = 10
HISTORY_DAYS = 30
PER_MINUTE = 10
PER_DAY = 200
ACTION_TTL = timedelta(minutes=10)
# The shared demo: per visitor (demo session) and for all visitors together
DEMO_PER_MINUTE = 3
DEMO_PER_SESSION = 20          # per 2-hour demo session
DEMO_PER_DAY = 300             # whole demo account
DEMO_ACTION_NOTE = "The demo is read-only, so this can't be applied. Sign up to do this with your own money."

SYSTEM_PROMPT = """You are Vaulta's assistant for one user's personal finances in India.
Today is {today}.
Rules:
- Answer only from tool results. Call tools for every number; never estimate or invent transactions, amounts or dates.
- If the tools don't cover the question or the data has gaps, say so plainly.
- Write amounts in INR with Indian digit grouping: ₹1,23,456.
- Spending excludes transfers between the user's own accounts, refunds are netted, money lent isn't spending.
- To change anything (budgets, categories, tags, kinds, cash expenses, goals) call the action tool; it only proposes the
  change and the user confirms it on a card. Don't claim a change is done.
- No investment, tax, insurance or credit advice. You may describe the user's own spending and budgets.
- Be brief: 1–4 sentences. Tables of figures are shown to the user separately when you call tools."""


class ChatLimit(Exception):
    """Rate limit hit; the route answers 429."""


class ActionUnavailable(Exception):
    """Token unknown, someone else's, expired or already used."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _check_demo_limits(db: Session, user: User) -> None:
    # Per visitor (demo session), shared by every API worker (app/core/ratelimit.py)
    if not ratelimit.hit("demo-chat-session", user.demo_session, DEMO_PER_SESSION, 7200):
        raise ChatLimit("That's the end of the demo's questions for this visit. Sign up to keep asking about your own money.")
    if not ratelimit.hit("demo-chat-minute", user.demo_session, DEMO_PER_MINUTE, 60):
        raise ChatLimit("That's a lot of questions at once. Try again in a minute.")
    day = db.query(ChatMessage.id).filter(ChatMessage.user_id == user.id, ChatMessage.role == "user",
                                          ChatMessage.created_at >= datetime.now(timezone.utc) - timedelta(days=1)).count()
    if day >= DEMO_PER_DAY:
        raise ChatLimit("The demo has answered a lot of questions today. Try again tomorrow, or sign up.")


def _check_limits(db: Session, user: User) -> None:
    if getattr(user, "demo_session", None):
        return _check_demo_limits(db, user)
    now = datetime.now(timezone.utc)
    sent = db.query(ChatMessage.created_at).filter(ChatMessage.user_id == user.id, ChatMessage.role == "user",
                                                   ChatMessage.created_at >= now - timedelta(days=1)).all()
    if len(sent) >= PER_DAY:
        raise ChatLimit("You've reached today's chat limit. It resets in 24 hours.")
    if sum(1 for (at,) in sent if at >= now - timedelta(minutes=1)) >= PER_MINUTE:
        raise ChatLimit("That's a lot of questions at once. Try again in a minute.")


def purge_old(db: Session, user_id: Optional[uuid.UUID] = None) -> int:
    """Delete history older than HISTORY_DAYS (one user, or everyone when called by the scheduler)."""
    q = db.query(ChatMessage).filter(ChatMessage.created_at < datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS))
    if user_id:
        q = q.filter(ChatMessage.user_id == user_id)
    n = q.delete(synchronize_session=False)
    db.commit()
    return n


def history(db: Session, user: User, session_id: uuid.UUID) -> list[ChatMessage]:
    rows = (db.query(ChatMessage).filter(ChatMessage.user_id == user.id, ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.role).limit(HISTORY_TURNS * 2).all())
    return list(reversed(rows))


def _save_turn(db: Session, user: User, session_id: uuid.UUID, question: str, answer: str) -> None:
    now = datetime.now(timezone.utc)
    db.add(ChatMessage(user_id=user.id, session_id=session_id, role="user", content=question, created_at=now))
    db.add(ChatMessage(user_id=user.id, session_id=session_id, role="assistant", content=answer,
                       created_at=now + timedelta(microseconds=1)))
    db.flush()
    keep = {m.id for m in history(db, user, session_id)}
    db.query(ChatMessage).filter(ChatMessage.user_id == user.id, ChatMessage.session_id == session_id,
                                 ChatMessage.id.notin_(keep)).delete(synchronize_session=False)
    db.commit()


def _new_action(db: Session, user: User, session_id: uuid.UUID, tool: str, args: dict, summary: str) -> dict:
    token = secrets.token_urlsafe(32)
    db.add(ChatAction(user_id=user.id, session_id=session_id, token_hash=_hash(token), tool=tool, args=args,
                      summary=summary, expires_at=datetime.now(timezone.utc) + ACTION_TTL))
    db.commit()
    return {"token": token, "tool": tool, "summary": summary, "expires_in_seconds": int(ACTION_TTL.total_seconds()),
            "read_only": is_demo(user), "note": DEMO_ACTION_NOTE if is_demo(user) else None}


def handle_message(db: Session, user: User, message: str, session_id: Optional[uuid.UUID] = None) -> dict:
    _check_limits(db, user)
    purge_old(db, user.id)
    session_id = session_id or uuid.uuid4()
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(today=clock.today().strftime("%A %d %B %Y"))}]
    messages += [{"role": m.role, "content": m.content} for m in history(db, user, session_id)]
    messages.append({"role": "user", "content": message})

    tables, actions, tools_used = [], [], []
    reply: Optional[str] = None
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            if time.monotonic() > deadline:
                raise llm.LLMError("timeout")
            answer = llm.complete(messages, TOOL_SCHEMAS)
            calls = answer.get("tool_calls") or []
            if not calls:
                reply = (answer.get("content") or "").strip()
                break
            messages.append({"role": "assistant", "content": answer.get("content") or "", "tool_calls": calls})
            for call in calls:
                name = call["function"]["name"]
                tools_used.append(name)
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                    if name in READ_TOOLS:
                        result = READ_TOOLS[name](db, user, args)
                        if (t := table_for(name, result)) and len(tables) < 3:
                            tables.append(t)
                    elif name in ACTION_TOOLS:
                        resolved, summary = propose(db, user, name, args)
                        actions.append(_new_action(db, user, session_id, name, resolved, summary))
                        result = {"status": "awaiting_user_confirmation", "summary": summary}
                    else:
                        result = {"error": f"unknown tool {name}"}
                except ToolError as e:
                    result = {"error": str(e)}
                except (ValueError, TypeError) as e:
                    result = {"error": f"bad arguments: {e}"}
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(llm_safe(result))})
        if reply is None:
            reply = "I couldn't work that out in a few steps. Could you ask it more specifically?"
    except llm.LLMError as e:
        logger.warning(f"chat: LLM unavailable for user={user_ref(user.id)}: {e.__class__.__name__}")
        timed_out = str(e) == "timeout"
        reply = ("That took too long to answer. Please try again, or ask something narrower." if timed_out
                 else "I can't reach the AI service right now. Your dashboard and reports still work.")
    if actions and not reply:
        reply = "Here's what I'll do. Confirm below."
    _save_turn(db, user, session_id, message, reply)
    return {"reply": reply, "session_id": str(session_id), "tables": tables, "actions": actions, "tools_used": tools_used}


def resolve_action(db: Session, user: User, token: str, confirm: bool) -> dict:
    """Run (or cancel) a proposed action. Single use, 10 minutes, only for the user it was made for."""
    action = db.query(ChatAction).filter(ChatAction.token_hash == _hash(token), ChatAction.user_id == user.id).first()
    if action is None or action.used_at is not None or action.expires_at < datetime.now(timezone.utc):
        raise ActionUnavailable("This confirmation has expired or was already used. Ask again to get a new one.")
    action.used_at = datetime.now(timezone.utc)
    action.outcome = "confirmed" if confirm else "cancelled"
    db.commit()   # mark used before running, so a retry can't run it twice
    if not confirm:
        message = f"Cancelled: {action.summary}."
    else:
        try:
            message = execute(db, user, action.tool, action.args)
        except ToolError as e:
            message = f"Couldn't do that: {e}"
    db.add(ChatMessage(user_id=user.id, session_id=action.session_id, role="assistant", content=message))
    db.commit()
    return {"ok": confirm, "message": message}
