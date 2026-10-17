"""
The guided tour's state and the getting-started checklist (Phase 8). Both live in users.onboarding (JSON):

  tour        {"status": "new" | "active" | "done" | "skipped", "step": n}: where the user is in the tour, so it resumes
              on any device; replayable from Settings and the "?" button
  checklist   {"dismissed": bool}; items tick from what the user has actually done (server data), never from clicks
  *_opened_at when the review queue and a report were first opened (GET /api/review, GET /api/reports/{id})

Neither exists for the demo: the routes say "available": false. Sample rows (simulations) never tick anything: every
query here goes through the sample filter (core/samples.py; tests/test_samples.py checks the checklist).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core import clock
from app.core.demo import is_demo
from app.models.chat import ChatMessage
from app.models.correction import Correction
from app.models.inbound import InboundEvent
from app.models.transaction import Budget, Transaction
from app.models.transaction_source import StatementSourceType, TransactionSourceRecord

TOUR_STATUSES = ("new", "active", "done", "skipped")
KEYS = ("tour", "checklist", "review_opened_at", "report_opened_at")     # what this module keeps in users.onboarding

# (id, title, link): the order shown. Links open the place where the item is done.
ITEMS = [
    ("verify_email", "Confirm your email address", "/verify-email"),
    ("first_import", "Import a bank statement", "/connect?do=import"),
    ("first_alert", "Forward your first bank alert", "/connect#forwarding"),
    ("telegram", "Link Telegram for quick entries", "/settings#telegram"),
    ("cash_expense", "Log a cash expense", "/cash"),
    ("budget", "Set a monthly budget", "/budgets"),
    ("review", "Open your review queue", "/review"),
    ("ask_ai", "Ask the assistant a question", "/?ask=1"),
    ("recategorise", "Change a transaction's category", "/transactions"),
    ("report", "Open a report", "/reports"),
]


def state(user) -> dict:
    return dict(user.onboarding or {})


def save(db: Session, user, **changes) -> None:
    user.onboarding = {**state(user), **changes}
    db.commit()


def note_opened(db: Session, user, what: str) -> None:
    """Record the first time the review queue or a report is opened (a checklist event)."""
    key = f"{what}_opened_at"
    if is_demo(user) or state(user).get(key):
        return
    save(db, user, **{key: clock.now().isoformat()})


def tour(user) -> dict:
    t = {"status": "new", "step": 0, **(state(user).get("tour") or {})}
    return {"available": not is_demo(user), **t}


def set_tour(db: Session, user, status: Optional[str], step: Optional[int]) -> dict:
    t = tour(user)
    t.pop("available")
    if status is not None:
        t["status"] = status
        if status in ("done", "skipped"):
            t[f"{status}_at"] = clock.now().isoformat()
        if status == "active" and step is None:
            t["step"] = 0                                   # replaying starts at the beginning
    if step is not None:
        t["step"] = step
    save(db, user, tour=t)
    return tour(user)


def _done(db: Session, user, email_verified: bool) -> dict[str, bool]:
    uid = user.id
    s = state(user)
    return {
        "verify_email": email_verified,
        "first_import": db.query(TransactionSourceRecord.id).filter(
            TransactionSourceRecord.user_id == uid,
            TransactionSourceRecord.source.notin_((StatementSourceType.email_alert, StatementSourceType.manual))).first() is not None,
        "first_alert": db.query(InboundEvent.id).filter(InboundEvent.user_id == uid, InboundEvent.outcome == "parsed").first() is not None,
        "telegram": user.telegram_chat_id is not None,
        "cash_expense": db.query(Transaction.id).filter(Transaction.user_id == uid, Transaction.cash_flow == "spend").first() is not None,
        "budget": db.query(Budget.id).filter(Budget.user_id == uid, Budget.is_active.is_(True)).first() is not None,
        "review": bool(s.get("review_opened_at")),
        "ask_ai": db.query(ChatMessage.id).filter(ChatMessage.user_id == uid, ChatMessage.role == "user").first() is not None,
        "recategorise": db.query(Correction.id).filter(Correction.user_id == uid, Correction.field == "category").first() is not None,
        "report": bool(s.get("report_opened_at")),
    }


def checklist(db: Session, user, email_verified: bool) -> dict:
    if is_demo(user):
        return {"available": False, "items": [], "done": 0, "total": 0, "dismissed": True}
    done = _done(db, user, email_verified)
    items = [{"id": i, "title": title, "link": link, "done": done[i]} for i, title, link in ITEMS]
    n = sum(1 for i in items if i["done"])
    return {"available": True, "items": items, "done": n, "total": len(items),
            "percent": round(100 * n / len(items)), "dismissed": bool((state(user).get("checklist") or {}).get("dismissed"))}


def set_checklist(db: Session, user, dismissed: bool) -> None:
    save(db, user, checklist={"dismissed": dismissed})
