"""
Tools the chat assistant can call.

Read tools are thin wrappers over services/analytics.py. Action tools never
write: they validate and resolve their target, then become a pending
ChatAction that runs only when the user confirms (services/chat.py).

Everything a tool returns to the model goes through llm_safe(), which keeps
merchant names, categories, amounts, dates, kinds and person display labels
and drops raw narrations, references, UTRs, masked UPI IDs and notes.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import clock
from app.models.person import Person
from app.models.transaction import Budget, KIND_DIRECTIONS, Transaction, TransactionKind
from app.models.user import User
from app.schemas.transaction import CATEGORIES, ManualTransactionCreate, TransactionUpdate
from app.services import analytics, transaction_service
from app.services.budgets import create_or_reactivate
from app.services.detection import run_detection
from app.services.keys import merchant_key
from app.services.people import set_tag
from app.services.recurring import add_months
from app.services.rules import upsert_rule

MAX_SEARCH_RESULTS = 50
WHAT_IF_BASELINE_MONTHS = 3

# Never sent to the model, wherever they appear in a result
PRIVATE_KEYS = {"merchant_raw", "description_raw", "counterparty_raw", "reference", "utr", "vpa", "masked_vpa",
                "raw_row", "raw_source_data", "notes", "idempotency_key"}


class ToolError(Exception):
    """Bad arguments or nothing found; the message goes back to the model."""


def llm_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: llm_safe(v) for k, v in value.items() if k not in PRIVATE_KEYS}
    if isinstance(value, (list, tuple)):
        return [llm_safe(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, uuid.UUID)):
        return str(value)
    return value


def inr(v) -> str:
    """₹1,23,456.50 — Indian digit grouping."""
    v = Decimal(v).quantize(Decimal("0.01"))
    sign, (whole, frac) = ("-" if v < 0 else ""), f"{abs(v):.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    head = ",".join(re.findall(r"\d{1,2}", head[::-1]))[::-1] if head else ""
    out = f"{head},{tail}" if head else tail
    return f"{sign}₹{out}" + ("" if frac == "00" else f".{frac}")


# ── Argument helpers ──────────────────────────────────────────────────────────

def _date(value, name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ToolError(f"{name} must be a date like 2024-06-30")


def _month(value, name: str = "month") -> date:
    v = str(value or clock.today().isoformat()[:7])
    try:
        return date.fromisoformat(f"{v[:7]}-01")
    except ValueError:
        raise ToolError(f"{name} must look like 2024-06")


def _amount(value, name: str = "amount") -> Decimal:
    try:
        v = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ToolError(f"{name} must be a number")
    if v <= 0 or v > Decimal("10000000"):
        raise ToolError(f"{name} must be between 0 and 1,00,00,000")
    return v


def _category(value) -> Optional[str]:
    if value is None or str(value).lower() in ("overall", "total", "all"):
        return None
    match = next((c for c in CATEGORIES if c.lower() == str(value).strip().lower()), None)
    if not match:
        raise ToolError(f"Unknown category '{value}'. Categories: {', '.join(sorted(CATEGORIES))}")
    return match


def _owned_txn(db: Session, user: User, txn_id) -> Transaction:
    try:
        tid = uuid.UUID(str(txn_id))
    except ValueError:
        raise ToolError("transaction_id must be an id from search_transactions")
    t = db.query(Transaction).filter(Transaction.id == tid, Transaction.user_id == user.id).first()
    if t is None:
        raise ToolError("No such transaction")
    return t


def _label(t: Transaction, people: dict) -> str:
    if t.person_id and t.person_id in people:
        return people[t.person_id]
    return t.merchant_clean or "Unrecognized merchant"


# ── Read tools ────────────────────────────────────────────────────────────────

def _range(args) -> tuple[date, date]:
    start, end = _date(args.get("start"), "start"), _date(args.get("end"), "end")
    if end < start:
        raise ToolError("end is before start")
    return start, end


def search_transactions(db: Session, user: User, args: dict) -> dict:
    q = db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.is_split.is_(False))
    if args.get("start"):
        q = q.filter(Transaction.transaction_date >= analytics.bounds(_date(args["start"], "start"), date.max)[0])
    if args.get("end"):
        q = q.filter(Transaction.transaction_date <= analytics.bounds(date.min, _date(args["end"], "end"))[1])
    if args.get("category"):
        q = q.filter(Transaction.category == _category(args["category"]))
    if args.get("merchant"):
        q = q.filter(Transaction.merchant_clean.ilike(f"%{args['merchant']}%"))
    if args.get("min_amount") is not None:
        q = q.filter(Transaction.amount >= _amount(args["min_amount"], "min_amount"))
    if args.get("max_amount") is not None:
        q = q.filter(Transaction.amount <= _amount(args["max_amount"], "max_amount"))
    people = {p.id: p.display_name for p in db.query(Person).filter(Person.user_id == user.id)}
    if args.get("query"):
        term = f"%{args['query']}%"
        person_ids = [pid for pid, name in people.items() if args["query"].lower() in name.lower()]
        # matching may look at the narration server-side; the narration itself is never returned
        q = q.filter(or_(Transaction.merchant_clean.ilike(term), Transaction.category.ilike(term),
                         Transaction.merchant_raw.ilike(term), Transaction.person_id.in_(person_ids)))
    limit = max(1, min(int(args.get("limit") or 20), MAX_SEARCH_RESULTS))
    rows = q.order_by(Transaction.transaction_date.desc()).limit(limit).all()
    return {"count": len(rows), "transactions": [
        {"id": str(t.id), "date": t.transaction_date.date().isoformat(), "merchant": _label(t, people),
         "category": t.category, "amount": analytics.money(t.amount), "direction": t.direction.value, "kind": t.kind.value}
        for t in rows]}


def what_if_reduce(db: Session, user: User, args: dict) -> dict:
    """Saving from cutting a category or merchant by `percent`, on its average of the last full months."""
    target = str(args.get("category_or_merchant") or "").strip()
    try:
        percent = Decimal(str(args.get("percent")))
        horizon = int(args.get("horizon_months") or 12)
    except (InvalidOperation, ValueError):
        raise ToolError("percent and horizon_months must be numbers")
    if not 0 < percent <= 100 or not 1 <= horizon <= 120:
        raise ToolError("percent must be 1–100 and horizon_months 1–120")
    first_of_month = clock.today().replace(day=1)
    months = [analytics.month_bounds(add_months(first_of_month, -k)) for k in range(WHAT_IF_BASELINE_MONTHS, 0, -1)]
    category = next((c for c in CATEGORIES if c.lower() == target.lower()), None)
    group_by, match = ("category", category) if category else ("merchant", target.lower())
    totals = []
    for start, end in months:
        groups = analytics.spend_summary(db, user.id, start, end, group_by)["groups"]
        totals.append(sum((g["total"] for g in groups if (g["label"] if category else g["label"].lower()) == match), analytics.ZERO))
    if not any(totals):
        raise ToolError(f"No spending on '{target}' in the last {WHAT_IF_BASELINE_MONTHS} full months")
    average = analytics.money(sum(totals) / len(totals))
    monthly_saving = analytics.money(average * percent / 100)
    return {"target": category or target, "as": group_by, "baseline_months": [s.isoformat()[:7] for s, _ in months],
            "monthly_totals": totals, "monthly_average": average, "percent": str(percent),
            "monthly_saving": monthly_saving, "horizon_months": horizon, "total_saving": monthly_saving * horizon}


READ_TOOLS: dict[str, Callable[[Session, User, dict], Any]] = {
    "spend_summary": lambda db, u, a: analytics.spend_summary(db, u.id, *_range(a), a.get("group_by") or "category"),
    "top_merchants": lambda db, u, a: {"merchants": analytics.top_merchants(db, u.id, *_range(a), int(a.get("n") or 5))},
    "compare_periods": lambda db, u, a: analytics.compare_periods(
        db, u.id, _date(a.get("a_start"), "a_start"), _date(a.get("a_end"), "a_end"),
        _date(a.get("b_start"), "b_start"), _date(a.get("b_end"), "b_end"), a.get("group_by") or "category"),
    "budget_status": lambda db, u, a: analytics.budget_status(db, u.id, _month(a.get("month"))),
    "recurring_overview": lambda db, u, a: analytics.recurring_overview(db, u.id),
    "upcoming": lambda db, u, a: {"upcoming": analytics.upcoming(db, u.id, int(a.get("days") or 14))},
    "person_balances": lambda db, u, a: {"people": analytics.person_balances(db, u.id)},
    "income_summary": lambda db, u, a: analytics.income_summary(db, u.id, *_range(a)),
    "savings_rate": lambda db, u, a: analytics.savings_rate(db, u.id, *_range(a)),
    "forecast_month_end": lambda db, u, a: analytics.forecast_month_end(db, u.id, _month(a.get("month"))),
    "safe_to_spend_today": lambda db, u, a: analytics.safe_to_spend_today(db, u.id),
    "search_transactions": search_transactions,
    "what_if_reduce": what_if_reduce,
}


# ── Action tools: propose (validate + resolve) now, execute on confirmation ───

def _resolve_merchant(db: Session, user: User, name: str) -> tuple[str, str]:
    """(merchant key, display label) for a merchant the user has transactions with."""
    needle = name.strip().lower()
    found: dict[str, str] = {}
    for t in db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.person_id.is_(None)):
        if (t.merchant_clean and needle in t.merchant_clean.lower()) or needle in merchant_key(t):
            found[merchant_key(t)] = t.merchant_clean or merchant_key(t).title()
    exact = {k: v for k, v in found.items() if v.lower() == needle}
    found = exact or found
    if not found:
        raise ToolError(f"No transactions from a merchant matching '{name}'")
    if len(found) > 1:
        raise ToolError(f"'{name}' matches several merchants: {', '.join(sorted(set(found.values())))}. Which one?")
    return next(iter(found.items()))


def _resolve_person(db: Session, user: User, name: str) -> Person:
    people = [p for p in db.query(Person).filter(Person.user_id == user.id, Person.merged_into_id.is_(None))]
    needle = name.strip().lower()
    matches = [p for p in people if p.display_name.lower() == needle] or [p for p in people if needle in p.display_name.lower()]
    if not matches:
        raise ToolError(f"No person matching '{name}'")
    if len(matches) > 1:
        raise ToolError(f"'{name}' matches {', '.join(p.display_name for p in matches)}. Which one?")
    return matches[0]


def propose(db: Session, user: User, tool: str, args: dict) -> tuple[dict, str]:
    """Validate an action and return (resolved args, one-line summary for the confirmation card)."""
    if tool == "set_budget":
        category, amount = _category(args.get("category")), _amount(args.get("amount"))
        return {"category": category, "amount": str(amount)}, f"Set a {inr(amount)} monthly budget for {category or 'all spending'}"
    if tool == "remove_budget":
        category = _category(args.get("category"))
        exists = db.query(Budget).filter(Budget.user_id == user.id, Budget.is_active.is_(True),
                                         Budget.category.is_(None) if category is None else Budget.category == category).first()
        if not exists:
            raise ToolError(f"There's no budget for {category or 'all spending'}")
        return {"category": category}, f"Remove the {category or 'overall'} budget ({inr(exists.monthly_limit)} a month)"
    if tool == "recategorize":
        category = _category(args.get("category"))
        if category is None:
            raise ToolError("category is required")
        target = str(args.get("merchant_or_transaction") or "")
        try:
            uuid.UUID(target)
            t = _owned_txn(db, user, target)
            return ({"mode": "transaction", "transaction_id": str(t.id), "category": category},
                    f"Change {t.merchant_clean or 'this transaction'} on {t.transaction_date:%d %b} ({inr(t.amount)}) to {category}")
        except ValueError:
            pass
        key, label = _resolve_merchant(db, user, target)
        if args.get("apply_to_all", True):
            return ({"mode": "rule", "merchant_key": key, "merchant": label, "category": category},
                    f"File all {label} transactions, past and future, under {category}")
        ids = [str(t.id) for t in db.query(Transaction).filter(Transaction.user_id == user.id) if merchant_key(t) == key]
        return ({"mode": "existing", "transaction_ids": ids, "category": category},
                f"Change {len(ids)} existing {label} transaction{'s' if len(ids) != 1 else ''} to {category}")
    if tool == "tag_person":
        tag = str(args.get("tag") or "")
        if tag not in ("Rent", "Splits", "Family", "Friend", "Lent", "Other"):
            raise ToolError("tag must be one of Rent, Splits, Family, Friend, Lent, Other")
        person = _resolve_person(db, user, str(args.get("person") or ""))
        return {"person_id": str(person.id), "tag": tag}, f"Tag {person.display_name} as {tag}"
    if tool == "mark_kind":
        t = _owned_txn(db, user, args.get("transaction_id"))
        try:
            kind = TransactionKind(str(args.get("kind")))
        except ValueError:
            raise ToolError(f"kind must be one of {', '.join(k.value for k in TransactionKind)}")
        if t.direction.value not in KIND_DIRECTIONS[kind]:
            raise ToolError(f"A {t.direction.value} can't be '{kind.value}'")
        return ({"transaction_id": str(t.id), "kind": kind.value},
                f"Mark {t.merchant_clean or 'the transaction'} on {t.transaction_date:%d %b} ({inr(t.amount)}) as {kind.value}")
    if tool == "add_cash_expense":
        amount = _amount(args.get("amount"))
        description = str(args.get("description") or "").strip()[:100]
        if not description:
            raise ToolError("description is required")
        day = _date(args.get("date") or clock.today().isoformat(), "date")
        if day > clock.today():
            raise ToolError("date can't be in the future")
        return ({"amount": str(amount), "description": description, "date": day.isoformat()},
                f"Add a cash expense: {description}, {inr(amount)} on {day:%d %b %Y}")
    raise ToolError(f"Unknown action {tool}")


def execute(db: Session, user: User, tool: str, args: dict) -> str:
    """Run a confirmed action. Returns what was done."""
    if tool == "set_budget":
        category, amount = args["category"], Decimal(args["amount"])
        active = db.query(Budget).filter(Budget.user_id == user.id, Budget.is_active.is_(True),
                                         Budget.category.is_(None) if category is None else Budget.category == category).first()
        if active:
            active.monthly_limit = amount
            db.commit()
        else:
            create_or_reactivate(db, user, category, amount)
        return f"Budget set: {inr(amount)} a month for {category or 'all spending'}."
    if tool == "remove_budget":
        category = args["category"]
        for b in db.query(Budget).filter(Budget.user_id == user.id, Budget.is_active.is_(True),
                                         Budget.category.is_(None) if category is None else Budget.category == category):
            b.is_active = False
        db.commit()
        return f"Removed the {category or 'overall'} budget."
    if tool == "recategorize":
        if args["mode"] == "rule":
            upsert_rule(db, user, args["merchant_key"], args["merchant"], "category", args["category"], "manual")
            return f"All {args['merchant']} transactions are now {args['category']}."
        ids = [args["transaction_id"]] if args["mode"] == "transaction" else args["transaction_ids"]
        for tid in ids:
            transaction_service.update_transaction(db, _owned_txn(db, user, tid), TransactionUpdate(category=args["category"]))
        return f"Changed {len(ids)} transaction{'s' if len(ids) != 1 else ''} to {args['category']}."
    if tool == "tag_person":
        person = db.query(Person).filter(Person.id == uuid.UUID(args["person_id"]), Person.user_id == user.id).one()
        set_tag(person, args["tag"])
        db.commit()
        run_detection(db, user)
        return f"{person.display_name} is tagged {args['tag']}."
    if tool == "mark_kind":
        transaction_service.update_transaction(db, _owned_txn(db, user, args["transaction_id"]), TransactionUpdate(kind=args["kind"]))
        return f"Marked as {args['kind']}."
    if tool == "add_cash_expense":
        transaction_service.create_manual_transaction(db, user, ManualTransactionCreate(
            client_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"chat|{user.id}|{args}")),
            date=args["date"], amount=args["amount"], merchant=args["description"], payment_method="cash"))
        return f"Added {args['description']}, {inr(Decimal(args['amount']))}."
    raise ToolError(f"Unknown action {tool}")


ACTION_TOOLS = ("set_budget", "remove_budget", "recategorize", "tag_person", "mark_kind", "add_cash_expense")


# ── Tables shown in the chat panel (computed here, not typed by the model) ────

def table_for(tool: str, result: dict) -> Optional[dict]:
    if tool in ("spend_summary", "top_merchants"):
        groups = result.get("groups") or result.get("merchants") or []
        return {"title": "Spending", "columns": ["", "Spent", "Count"],
                "rows": [[g["label"], inr(g["total"]), g["count"]] for g in groups[:8]]}
    if tool == "compare_periods":
        return {"title": f"{result['a']['start']} – {result['a']['end']} vs {result['b']['start']} – {result['b']['end']}",
                "columns": ["", "This", "Before", "Change"],
                "rows": [[r["label"], inr(r["a"]), inr(r["b"]), inr(r["delta"])] for r in result["rows"][:8]]
                + [["Total", inr(result["a"]["total"]), inr(result["b"]["total"]), inr(result["delta"])]]}
    if tool == "budget_status":
        lines = ([result["overall"]] if result["overall"] else []) + result["categories"]
        return {"title": f"Budgets {result['month']}", "columns": ["", "Spent", "Limit", "Left"],
                "rows": [[b["category"], inr(b["spent"]), inr(b["limit"]), inr(b["remaining"])] for b in lines]} if lines else None
    if tool in ("recurring_overview", "upcoming"):
        series = result.get("series") or result.get("upcoming") or []
        return {"title": "Recurring", "columns": ["", "Amount", "Next"],
                "rows": [[s["name"], inr(s["typical_amount"]), s["next_expected"]] for s in series[:8]]} if series else None
    if tool == "person_balances":
        return {"title": "People", "columns": ["", "Paid", "Received", "Balance"],
                "rows": [[p["name"], inr(p["paid_total"]), inr(p["received_total"]), inr(p["balance"])] for p in result["people"][:8]]}
    if tool == "income_summary":
        return {"title": "Income", "columns": ["", "Amount"], "rows": [[s["label"], inr(s["total"])] for s in result["sources"][:8]]}
    if tool == "search_transactions":
        return {"title": "Transactions", "columns": ["Date", "", "Amount", "Category"],
                "rows": [[t["date"], t["merchant"], inr(t["amount"]), t["category"] or ""] for t in result["transactions"][:10]]}
    return None


# ── Schemas sent to the model ─────────────────────────────────────────────────

def _fn(name: str, description: str, properties: dict, required: tuple = ()) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": properties, "required": list(required)}}}


_DATE = {"type": "string", "description": "YYYY-MM-DD"}
_GROUP = {"type": "string", "enum": ["category", "merchant", "person", "day", "week", "month"]}
_MONTH = {"type": "string", "description": "YYYY-MM (default: this month)"}

TOOL_SCHEMAS = [
    _fn("spend_summary", "Net spending in a date range, grouped.", {"start": _DATE, "end": _DATE, "group_by": _GROUP}, ("start", "end")),
    _fn("top_merchants", "Merchants with the most spending in a date range.", {"start": _DATE, "end": _DATE, "n": {"type": "integer"}}, ("start", "end")),
    _fn("compare_periods", "Spending in period A vs period B, grouped.",
        {"a_start": _DATE, "a_end": _DATE, "b_start": _DATE, "b_end": _DATE, "group_by": _GROUP}, ("a_start", "a_end", "b_start", "b_end")),
    _fn("budget_status", "Budgets vs spending for a month.", {"month": _MONTH}),
    _fn("recurring_overview", "Recurring payments/subscriptions and the monthly committed total.", {}),
    _fn("upcoming", "Recurring payments due in the next N days.", {"days": {"type": "integer"}}),
    _fn("person_balances", "People the user pays or is paid by, with who owes whom.", {}),
    _fn("income_summary", "Income in a date range by source.", {"start": _DATE, "end": _DATE}, ("start", "end")),
    _fn("savings_rate", "Income, spending and savings rate in a date range.", {"start": _DATE, "end": _DATE}, ("start", "end")),
    _fn("forecast_month_end", "Projected month-end spending at the current pace.", {"month": _MONTH}),
    _fn("safe_to_spend_today", "How much can be spent today and stay within this month's limit.", {}),
    _fn("search_transactions", "Find transactions. All filters optional.",
        {"query": {"type": "string"}, "start": _DATE, "end": _DATE, "category": {"type": "string"},
         "merchant": {"type": "string"}, "min_amount": {"type": "number"}, "max_amount": {"type": "number"},
         "limit": {"type": "integer", "description": f"max {MAX_SEARCH_RESULTS}"}}),
    _fn("what_if_reduce", "Savings from cutting a category or merchant by a percentage.",
        {"category_or_merchant": {"type": "string"}, "percent": {"type": "number"}, "horizon_months": {"type": "integer"}},
        ("category_or_merchant", "percent")),
    _fn("set_budget", "Propose a monthly budget (user must confirm). category 'overall' for a total cap.",
        {"category": {"type": "string"}, "amount": {"type": "number"}}, ("category", "amount")),
    _fn("remove_budget", "Propose removing a budget (user must confirm).", {"category": {"type": "string"}}, ("category",)),
    _fn("recategorize", "Propose changing the category of a transaction (by id) or a merchant (user must confirm).",
        {"merchant_or_transaction": {"type": "string"}, "category": {"type": "string"},
         "apply_to_all": {"type": "boolean", "description": "merchant only: also future transactions (default true)"}},
        ("merchant_or_transaction", "category")),
    _fn("tag_person", "Propose tagging a person (user must confirm).",
        {"person": {"type": "string"}, "tag": {"type": "string", "enum": ["Rent", "Splits", "Family", "Friend", "Lent", "Other"]}},
        ("person", "tag")),
    _fn("mark_kind", "Propose changing what a transaction is (user must confirm).",
        {"transaction_id": {"type": "string"}, "kind": {"type": "string", "enum": [k.value for k in TransactionKind]}},
        ("transaction_id", "kind")),
    _fn("add_cash_expense", "Propose adding a cash expense (user must confirm).",
        {"amount": {"type": "number"}, "description": {"type": "string"}, "date": _DATE}, ("amount", "description")),
]
