"""
The query layer: every number Vaulta shows, says in chat, or puts in a
report comes from here. Pure functions over kind-correct data, always
scoped by user_id.

Counting rules (one place):
  - spending = kind spend minus kind refund; income = kind income
  - transfers, reversals, lent/borrowed/repayment never count
  - a split transaction counts through its parts, never itself

Periods are inclusive dates (start, end). Amounts are Decimal; dates are ISO
strings in the returned dicts so chat and reports serialize them as-is.
"""

from __future__ import annotations

import calendar
import math
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core import clock
from app.models.category import Tag, TransactionTag
from app.models.goal import Goal
from app.models.person import Person
from app.models.recurring import RecurringSeries
from app.models.transaction import Budget, Transaction, TransactionKind
from app.services.categories import custom_subcategories, label as subcategory_label
from app.services.people import balances
from app.services.recurring import series_key

ZERO = Decimal("0.00")
GroupBy = Literal["category", "subcategory", "tag", "merchant", "person", "day", "week", "month"]

NET_SPEND = case(
    (Transaction.kind == TransactionKind.spend, Transaction.amount),
    (Transaction.kind == TransactionKind.refund, -Transaction.amount),
    else_=0,
)
SPEND_COUNT = case((Transaction.kind == TransactionKind.spend, 1))
SPEND_KINDS = (TransactionKind.spend, TransactionKind.refund)
COMMITTED_STATUSES = ("active", "missed")
MONTHLY_FACTOR = {"weekly": Decimal(52) / 12, "monthly": Decimal(1), "yearly": Decimal(1) / 12}


def money(v) -> Decimal:
    return Decimal(v or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (datetime.combine(start, time.min, tzinfo=timezone.utc),
            datetime.combine(end, time(23, 59, 59), tzinfo=timezone.utc))


def month_bounds(month: date) -> tuple[date, date]:
    first = month.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def counted(user_id: uuid.UUID, start: date, end: date) -> tuple:
    """Filters for rows that can affect totals in [start, end]."""
    lo, hi = bounds(start, end)
    return (
        Transaction.user_id == user_id,
        Transaction.is_split.is_(False),     # its parts count instead
        Transaction.transaction_date >= lo,
        Transaction.transaction_date <= hi,
    )


# ── Spending ──────────────────────────────────────────────────────────────────

def spend_summary(db: Session, user_id: uuid.UUID, start: date, end: date, group_by: GroupBy = "category") -> dict:
    """Net spend in the period, grouped. {total, count, groups: [{key, label, total, count}]} largest first."""
    keys = {
        "category": Transaction.category,
        "merchant": Transaction.merchant_clean,
        "person": Transaction.person_id,
        "day": func.date(Transaction.transaction_date),
        "week": func.date(func.date_trunc("week", Transaction.transaction_date)),
        "month": func.date(func.date_trunc("month", Transaction.transaction_date)),
    }
    keys["subcategory"] = Transaction.subcategory
    keys["tag"] = TransactionTag.tag_id
    key = keys[group_by]
    q = (
        db.query(key.label("key"), func.sum(NET_SPEND).label("total"), func.count(SPEND_COUNT).label("count"))
        .filter(*counted(user_id, start, end), Transaction.kind.in_(SPEND_KINDS))
        .group_by(key)
    )
    if group_by == "person":
        q = q.filter(Transaction.person_id.isnot(None))
    if group_by == "tag":
        # a transaction counts once under each of its tags, so tag totals can add up to more than the total.
        # A split part counts under its parent's tags.
        owner = func.coalesce(Transaction.split_parent_id, Transaction.id)
        q = q.join(TransactionTag, TransactionTag.transaction_id == owner)
    rows = q.all()
    names = {}
    if group_by == "person":
        names = {p.id: p.display_name for p in db.query(Person).filter(Person.user_id == user_id)}
    if group_by == "tag":
        names = {t.id: t.name for t in db.query(Tag).filter(Tag.user_id == user_id)}
    if group_by == "subcategory":
        custom = custom_subcategories(db, user_id)

    def label(k):
        if group_by == "category":
            return k or "Uncategorized"
        if group_by == "subcategory":
            return subcategory_label(k, custom) or "No subcategory"
        if group_by == "tag":
            return names.get(k, "Unknown tag")
        if group_by == "merchant":
            return k or "Unknown merchant"
        if group_by == "person":
            return names.get(k, "Unknown person")
        return k.isoformat()

    groups = [
        {"key": str(r.key) if r.key is not None else None, "label": label(r.key), "total": money(r.total), "count": r.count}
        for r in rows
    ]
    order = (lambda g: g["key"]) if group_by in ("day", "week", "month") else (lambda g: (-g["total"], g["label"]))
    groups.sort(key=order)
    return {
        "start": start.isoformat(), "end": end.isoformat(), "group_by": group_by,
        "total": money(sum((g["total"] for g in groups), ZERO)), "count": sum(g["count"] for g in groups),
        "groups": groups,
    }


def top_merchants(db: Session, user_id: uuid.UUID, start: date, end: date, n: int = 10) -> list[dict]:
    return spend_summary(db, user_id, start, end, "merchant")["groups"][:n]


def compare_periods(db: Session, user_id: uuid.UUID, a_start: date, a_end: date, b_start: date, b_end: date,
                    group_by: GroupBy = "category") -> dict:
    """Period A against period B. delta = A − B; delta_pct relative to B (None when B is 0)."""
    a = spend_summary(db, user_id, a_start, a_end, group_by)
    b = spend_summary(db, user_id, b_start, b_end, group_by)
    a_by, b_by = {g["label"]: g["total"] for g in a["groups"]}, {g["label"]: g["total"] for g in b["groups"]}

    def pct(x: Decimal, y: Decimal) -> Optional[Decimal]:
        return ((x - y) / y * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if y else None

    rows = [
        {"label": label, "a": a_by.get(label, ZERO), "b": b_by.get(label, ZERO),
         "delta": a_by.get(label, ZERO) - b_by.get(label, ZERO), "delta_pct": pct(a_by.get(label, ZERO), b_by.get(label, ZERO))}
        for label in sorted(set(a_by) | set(b_by))
    ]
    rows.sort(key=lambda r: -abs(r["delta"]))
    return {
        "a": {"start": a_start.isoformat(), "end": a_end.isoformat(), "total": a["total"]},
        "b": {"start": b_start.isoformat(), "end": b_end.isoformat(), "total": b["total"]},
        "delta": a["total"] - b["total"], "delta_pct": pct(a["total"], b["total"]), "rows": rows,
    }


# ── Income and savings ────────────────────────────────────────────────────────

def income_summary(db: Session, user_id: uuid.UUID, start: date, end: date) -> dict:
    """
    Income in the period by source: normalized merchant, else category, else
    "Other income". Never narration text (these labels reach the LLM).
    """
    by: dict[str, list] = {}
    for t in db.query(Transaction).filter(*counted(user_id, start, end), Transaction.kind == TransactionKind.income):
        label = t.merchant_clean or t.category or "Other income"
        entry = by.setdefault(label, [ZERO, 0])
        entry[0] += t.amount
        entry[1] += 1
    sources = sorted(({"label": k, "total": money(v[0]), "count": v[1]} for k, v in by.items()), key=lambda s: (-s["total"], s["label"]))
    return {"start": start.isoformat(), "end": end.isoformat(),
            "total": money(sum((s["total"] for s in sources), ZERO)), "count": sum(s["count"] for s in sources),
            "sources": sources}


def savings_rate(db: Session, user_id: uuid.UUID, start: date, end: date) -> dict:
    """(income − spend) / income, as a percentage. rate is None when there was no income."""
    income = income_summary(db, user_id, start, end)["total"]
    spend = spend_summary(db, user_id, start, end)["total"]
    rate = ((income - spend) / income * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if income else None
    return {"start": start.isoformat(), "end": end.isoformat(), "income": income, "spend": spend,
            "saved": income - spend, "rate_pct": rate}


# ── Budgets ───────────────────────────────────────────────────────────────────

def active_budgets(db: Session, user_id: uuid.UUID) -> dict[Optional[str], Decimal]:
    """{category: monthly limit}; the None key is the overall cap. Subcategory budgets: budget_status."""
    return {b.category: b.monthly_limit
            for b in db.query(Budget).filter(Budget.user_id == user_id, Budget.is_active.is_(True),
                                             Budget.subcategory.is_(None))}


def budget_status(db: Session, user_id: uuid.UUID, month: date) -> dict:
    start, end = month_bounds(month)
    budgets = active_budgets(db, user_id)
    spent = {g["label"]: g["total"] for g in spend_summary(db, user_id, start, end)["groups"]}
    total_spend = sum(spent.values(), ZERO)
    today = clock.today()
    days_left = (end - today).days if start <= today <= end else (0 if today > end else (end - start).days + 1)

    def line(category: Optional[str], limit: Decimal, used: Decimal) -> dict:
        return {"category": category or "Overall", "limit": money(limit), "spent": money(used),
                "remaining": money(limit - used), "pct": (used / limit * 100).quantize(Decimal("0.1")) if limit else None,
                "over": used > limit}

    categories = [line(c, limit, spent.get(c, ZERO)) for c, limit in sorted(budgets.items(), key=lambda kv: kv[0] or "") if c]
    sub_budgets = db.query(Budget).filter(Budget.user_id == user_id, Budget.is_active.is_(True), Budget.subcategory.isnot(None)).all()
    if sub_budgets:
        custom = custom_subcategories(db, user_id)
        sub_spent = {g["key"]: g["total"] for g in spend_summary(db, user_id, start, end, "subcategory")["groups"]}
        for b in sorted(sub_budgets, key=lambda b: (b.category, subcategory_label(b.subcategory, custom) or "")):
            categories.append({**line(subcategory_label(b.subcategory, custom) or b.subcategory, b.monthly_limit,
                                      sub_spent.get(b.subcategory, ZERO)), "group": b.category, "subcategory": b.subcategory})
    return {
        "month": start.isoformat()[:7], "days_left": days_left, "total_spend": money(total_spend),
        "overall": line(None, budgets[None], total_spend) if None in budgets else None,
        "categories": categories,
    }


# ── Recurring and people ──────────────────────────────────────────────────────

def monthly_equivalent(series: RecurringSeries) -> Decimal:
    return (Decimal(series.typical_amount) * MONTHLY_FACTOR[series.cadence]).quantize(Decimal("0.01"))


def series_view(s: RecurringSeries) -> dict:
    return {
        "id": str(s.id), "name": s.user_name or s.display_name, "cadence": s.cadence,
        "typical_amount": money(s.typical_amount), "monthly_amount": monthly_equivalent(s),
        "last_amount": money(s.last_amount), "last_date": s.last_date.isoformat(),
        "next_expected": s.next_expected.isoformat(), "occurrences": s.occurrences, "status": s.status,
        "type": s.user_type or s.type_guess, "category": s.category,
        "price_change": {"old": money(s.previous_amount), "new": money(s.typical_amount)} if s.previous_amount is not None else None,
        "user_status": s.user_status, "usage": s.usage,
    }


def _visible_series(db: Session, user_id: uuid.UUID) -> list[RecurringSeries]:
    rows = db.query(RecurringSeries).filter(RecurringSeries.user_id == user_id).order_by(RecurringSeries.next_expected).all()
    return [s for s in rows if s.user_status != "dismissed"]


def recurring_overview(db: Session, user_id: uuid.UUID) -> dict:
    series = _visible_series(db, user_id)
    return {
        "series": [series_view(s) for s in series],
        "monthly_committed": sum((monthly_equivalent(s) for s in series if s.status in COMMITTED_STATUSES), ZERO),
    }


def upcoming(db: Session, user_id: uuid.UUID, days: int = 14) -> list[dict]:
    """Committed series due from today through today + days."""
    today = clock.today()
    return [series_view(s) for s in _visible_series(db, user_id)
            if s.status in COMMITTED_STATUSES and today <= s.next_expected <= today + timedelta(days=days)]


def person_balances(db: Session, user_id: uuid.UUID) -> list[dict]:
    """Every person with transactions: totals and lent/borrowed balance. Largest money flow first."""
    people = db.query(Person).filter(Person.user_id == user_id, Person.merged_into_id.is_(None)).all()
    txns = db.query(Transaction).filter(Transaction.user_id == user_id, Transaction.person_id.isnot(None)).all()
    bal = balances(txns)
    today = clock.today()
    out = []
    for p in people:
        mine = [t for t in txns if t.person_id == p.id and t.kind != TransactionKind.reversal]
        if not mine:
            continue
        b = bal.get(p.id)
        out.append({
            "id": str(p.id), "name": p.display_name, "masked_vpa": p.masked_vpa, "tag": p.tag,
            "default_category": p.default_category, "default_kind": p.default_kind,
            "paid_total": money(sum((t.amount for t in mine if t.direction.value == "debit"), ZERO)),
            "received_total": money(sum((t.amount for t in mine if t.direction.value == "credit"), ZERO)),
            "transaction_count": len(mine),
            "last_date": max(t.transaction_date for t in mine).date().isoformat(),
            "owed_to_you": money(b.owed_to_you if b else ZERO), "you_owe": money(b.you_owe if b else ZERO),
            "balance": money(b.net if b else ZERO),
            "outstanding_days": (today - b.oldest_open).days if b and b.oldest_open else None,
        })
    return sorted(out, key=lambda v: -(v["paid_total"] + v["received_total"]))


# ── Forecast and safe-to-spend ────────────────────────────────────────────────

def _series_keys(db: Session, user_id: uuid.UUID) -> dict[str, RecurringSeries]:
    return {s.key: s for s in _visible_series(db, user_id) if s.status in COMMITTED_STATUSES}


def forecast_month_end(db: Session, user_id: uuid.UUID, month: date) -> dict:
    """
    Pace-based month-end spend: spend so far + recurring still due this month
    + (daily average of non-recurring spend so far) × days left.
    Past months: the actual total. Future months: recurring only.
    """
    start, end = month_bounds(month)
    today = clock.today()
    if today > end:
        actual = spend_summary(db, user_id, start, end)["total"]
        return {"month": start.isoformat()[:7], "so_far": actual, "recurring_due": ZERO, "discretionary_daily": ZERO,
                "days_left": 0, "forecast": actual}
    through = min(today, end)
    series = _series_keys(db, user_id)
    txns = (db.query(Transaction)
            .filter(*counted(user_id, start, through), Transaction.kind.in_(SPEND_KINDS)).all()) if today >= start else []
    so_far = money(sum((t.amount if t.kind == TransactionKind.spend else -t.amount for t in txns), ZERO))
    recurring_so_far = money(sum((t.amount for t in txns if t.kind == TransactionKind.spend and series_key(t)[0] in series), ZERO))
    days_elapsed = (through - start).days + 1 if today >= start else 0
    days_left = (end - through).days if today >= start else (end - start).days + 1
    discretionary_daily = money((so_far - recurring_so_far) / days_elapsed) if days_elapsed else ZERO
    after = through if today >= start else start - timedelta(days=1)
    due = [s for s in series.values() if after < s.next_expected <= end]
    recurring_due = money(sum((s.typical_amount for s in due), ZERO))
    return {
        "month": start.isoformat()[:7], "so_far": so_far, "recurring_due": recurring_due,
        "recurring_due_items": [{"name": s.user_name or s.display_name, "amount": money(s.typical_amount),
                                 "date": s.next_expected.isoformat()} for s in sorted(due, key=lambda s: s.next_expected)],
        "discretionary_daily": discretionary_daily, "days_left": days_left,
        "forecast": money(so_far + recurring_due + discretionary_daily * days_left),
    }


def month_limit(db: Session, user_id: uuid.UUID, month: date) -> tuple[Optional[Decimal], Optional[str]]:
    """
    The month's spending limit and what it is: the overall budget cap, else the
    sum of category budgets, else the month's income so far. (None, None) without any.
    """
    budgets = active_budgets(db, user_id)
    if None in budgets:
        return budgets[None], "overall budget"
    if budgets:
        return sum(budgets.values(), ZERO), "sum of category budgets"
    start, end = month_bounds(month)
    income = income_summary(db, user_id, start, min(end, clock.today()))["total"]
    return (income, "income this month") if income else (None, None)


OUTLOOK_AMBER_PCT = Decimal(90)   # forecast above 90% of the limit → amber; above 100% → red


def month_outlook(db: Session, user_id: uuid.UUID, month: date) -> dict:
    """The month-end forecast against the month's limit: green / amber / red."""
    f = forecast_month_end(db, user_id, month)
    limit, basis = month_limit(db, user_id, month)
    if limit is None:
        return {**f, "limit": None, "basis": None, "difference": None, "status": None}
    pct = f["forecast"] / limit * 100 if limit else Decimal(100)
    status = "red" if f["forecast"] > limit else "amber" if pct > OUTLOOK_AMBER_PCT else "green"
    return {**f, "limit": money(limit), "basis": basis, "difference": money(f["forecast"] - limit), "status": status}


def safe_to_spend_today(db: Session, user_id: uuid.UUID) -> dict:
    """
    What's left for today without going over the month's limit (month_limit):
    (limit − spend so far − recurring still due) ÷ days left including today.
    None when there's no limit to measure against.
    """
    today = clock.today()
    _, end = month_bounds(today)
    limit, basis = month_limit(db, user_id, today)
    f = forecast_month_end(db, user_id, today)
    days = (end - today).days + 1
    if limit is None:
        return {"date": today.isoformat(), "amount": None, "basis": None, "reason": "No budget or income this month to measure against."}
    remaining = money(limit - f["so_far"] - f["recurring_due"])
    return {"date": today.isoformat(), "amount": max(money(remaining / days), ZERO), "basis": basis,
            "limit": money(limit), "spent_so_far": f["so_far"], "recurring_due": f["recurring_due"],
            "remaining": remaining, "days_left_including_today": days}


# ── Goals ─────────────────────────────────────────────────────────────────────

GOAL_ESTIMATE_MONTHS = 3          # savings-rate estimate: average of the last 3 full months
DAYS_PER_MONTH = Decimal("30.44")


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def _after_months(start: date, months: Decimal) -> date:
    return start + timedelta(days=math.ceil(months * DAYS_PER_MONTH))


def monthly_savings_estimate(db: Session, user_id: uuid.UUID) -> Optional[Decimal]:
    """Average (income − spend) over the last full months; None without income in them."""
    first = clock.today().replace(day=1)
    start = (first - timedelta(days=1)).replace(day=1)
    for _ in range(GOAL_ESTIMATE_MONTHS - 1):
        start = (start - timedelta(days=1)).replace(day=1)
    s = savings_rate(db, user_id, start, first - timedelta(days=1))
    return money(s["saved"] / GOAL_ESTIMATE_MONTHS) if s["income"] else None


def goal_status(db: Session, goal: Goal, savings_estimate: Optional[Decimal] = None) -> dict:
    """
    Progress from the user's own contributions (goal entries, not transactions).
      required_monthly   what's left ÷ whole months to the target date (at least 1)
      pace               contributions so far ÷ months since the first one (at least 1)
      projected_date     when the pace reaches the target
      status             done | on_track (projected by the target date) | behind | not_started
    The savings-rate estimate is separate and labelled as an estimate.
    """
    today = clock.today()
    saved = money(sum((e.amount for e in goal.entries), ZERO))
    target = money(goal.target_amount)
    remaining = max(target - saved, ZERO)
    months_left = max(_months_between(today, goal.target_date), 1) if goal.target_date >= today else 0
    required = money(remaining / months_left) if months_left else (remaining if remaining else ZERO)
    first = min((e.entry_date for e in goal.entries), default=None)
    pace = money(saved / max(_months_between(first, today) + 1, 1)) if first and saved > 0 else ZERO
    projected = (today if remaining == 0 else _after_months(today, remaining / pace)) if pace > 0 else None
    if remaining == 0:
        status = "done"
    elif not goal.entries:
        status = "not_started"
    else:
        status = "on_track" if projected and projected <= goal.target_date else "behind"
    out = {
        "id": str(goal.id), "name": goal.name, "target_amount": target, "target_date": goal.target_date.isoformat(),
        "category": goal.category, "saved": saved, "remaining": remaining,
        "progress_pct": (saved / target * 100).quantize(Decimal("0.1")) if target else None,
        "months_left": months_left, "required_monthly": required, "monthly_pace": pace,
        "projected_date": projected.isoformat() if projected else None, "status": status,
        "entries": [{"id": str(e.id), "amount": money(e.amount), "date": e.entry_date.isoformat()} for e in goal.entries],
        "estimate": None, "category_spend": None,
    }
    if savings_estimate and savings_estimate > 0 and remaining > 0:
        out["estimate"] = {"monthly_savings": savings_estimate,
                           "projected_date": _after_months(today, remaining / savings_estimate).isoformat(),
                           "label": f"Estimate from your average savings over the last {GOAL_ESTIMATE_MONTHS} months"}
    if goal.category:
        start, end = month_bounds(today)
        this_month = next((g["total"] for g in spend_summary(db, goal.user_id, start, end)["groups"] if g["label"] == goal.category), ZERO)
        out["category_spend"] = {"category": goal.category, "this_month": this_month}
    return out


def goals_overview(db: Session, user_id: uuid.UUID) -> list[dict]:
    goals = db.query(Goal).filter(Goal.user_id == user_id).order_by(Goal.target_date, Goal.created_at).all()
    estimate = monthly_savings_estimate(db, user_id) if goals else None
    return [goal_status(db, g, estimate) for g in goals]
