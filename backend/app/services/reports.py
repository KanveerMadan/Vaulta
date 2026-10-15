"""
Weekly (Mon–Sun), monthly and annual reports. Every figure is computed by
services/analytics.py; the LLM only writes a short summary of the JSON and
may not introduce a number that isn't in it (checked; otherwise a template
summary is used).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

from sqlalchemy.orm import Session

from app.core import clock
from app.models.anomaly import Anomaly
from app.models.recurring import RecurringSeries
from app.models.report import Report
from app.models.transaction import Transaction, TransactionKind
from app.services import analytics, cash, llm
from app.services.anomalies import SPIKE_TRAILING_PERIODS, category_spikes
from app.services.chat_tools import inr, llm_safe
from app.services.recurring import CADENCES, CANCELLED_AFTER, series_key

logger = logging.getLogger(__name__)

PeriodType = Literal["weekly", "monthly", "annual"]
TOP_N = 5


# ── Periods ───────────────────────────────────────────────────────────────────

def period_for(period_type: PeriodType, day: date) -> tuple[date, date]:
    """The weekly (Mon–Sun) / monthly / annual period containing `day`."""
    if period_type == "weekly":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    if period_type == "monthly":
        return analytics.month_bounds(day)
    return date(day.year, 1, 1), date(day.year, 12, 31)


def previous_period(period_type: PeriodType, start: date) -> tuple[date, date]:
    return period_for(period_type, start - timedelta(days=1))


def next_period(period_type: PeriodType, end: date) -> tuple[date, date]:
    return period_for(period_type, end + timedelta(days=1))


def trailing_periods(period_type: PeriodType, start: date, n: int) -> list[tuple[date, date]]:
    periods, s = [], start
    for _ in range(n):
        p = previous_period(period_type, s)
        periods.insert(0, p)
        s = p[0]
    return periods


def label(period_type: PeriodType, start: date, end: date) -> str:
    if period_type == "weekly":
        return f"Week of {start:%d %b} – {end:%d %b %Y}"
    if period_type == "monthly":
        return f"{start:%B %Y}"
    return f"{start.year}"


# ── Sections ──────────────────────────────────────────────────────────────────

def _recurring_changes(db: Session, user_id: uuid.UUID, start: date, end: date) -> dict:
    series = [s for s in db.query(RecurringSeries).filter(RecurringSeries.user_id == user_id) if s.user_status != "dismissed"]

    def view(s):
        return {"name": s.user_name or s.display_name, "amount": analytics.money(s.typical_amount), "cadence": s.cadence}

    def stopped_on(s):
        return s.last_date + timedelta(days=int(CADENCES[s.cadence][2] * CANCELLED_AFTER))

    return {
        "new": [view(s) for s in series if s.established_on and start <= s.established_on <= end],
        "cancelled": [view(s) for s in series if s.status == "cancelled" and start <= stopped_on(s) <= end],
        "price_changed": [{**view(s), "old_amount": analytics.money(s.previous_amount)}
                          for s in series if s.previous_amount is not None and start <= s.last_date <= end],
    }


def _anomalies(db: Session, user_id: uuid.UUID, period_type: PeriodType, start: date, end: date) -> list[dict]:
    stored = (db.query(Anomaly).filter(Anomaly.user_id == user_id, Anomaly.occurred_on >= start, Anomaly.occurred_on <= end,
                                       Anomaly.type != "category_spike").order_by(Anomaly.occurred_on))
    found = [{"type": a.type, "date": a.occurred_on.isoformat(), **{k: v for k, v in a.details.items() if k != "transactions"}}
             for a in stored]
    if period_type != "annual":   # spikes vs the trailing periods of the same length
        periods = trailing_periods(period_type, start, SPIKE_TRAILING_PERIODS) + [(start, end)]
        found += [{"type": s["type"], "date": s["occurred_on"].isoformat(), **s["details"]}
                  for s in category_spikes(db, user_id, periods)]
    return found


def _people(db: Session, user_id: uuid.UUID) -> dict:
    owed = [p for p in analytics.person_balances(db, user_id) if p["balance"] != 0]
    return {
        "owed_to_you": [{"name": p["name"], "amount": p["balance"], "days": p["outstanding_days"]} for p in owed if p["balance"] > 0],
        "you_owe": [{"name": p["name"], "amount": -p["balance"], "days": p["outstanding_days"]} for p in owed if p["balance"] < 0],
    }


def _allowance(db: Session, user_id: uuid.UUID, start: date, end: date) -> dict:
    """
    Safe to spend in [start, end]: the month's limit (overall budget, else
    category budgets, else last full month's income) minus the recurring
    committed that month, as a daily allowance × the days in the period.
    """
    month_start, month_end = analytics.month_bounds(start)
    budgets = analytics.active_budgets(db, user_id)
    if None in budgets:
        limit, basis = budgets[None], "overall budget"
    elif budgets:
        limit, basis = sum(budgets.values(), analytics.ZERO), "category budgets"
    else:
        prev_start, prev_end = analytics.month_bounds(month_start - timedelta(days=1))
        limit, basis = analytics.income_summary(db, user_id, prev_start, prev_end)["total"], "last month's income"
    if not limit:
        return {"amount": None, "basis": None}
    committed = analytics.recurring_overview(db, user_id)["monthly_committed"]
    per_day = analytics.money((limit - committed) / ((month_end - month_start).days + 1))
    days = (end - start).days + 1
    return {"start": start.isoformat(), "end": end.isoformat(), "basis": basis, "monthly_limit": analytics.money(limit),
            "recurring_committed": committed, "per_day": max(per_day, analytics.ZERO),
            "amount": max(analytics.money(per_day * days), analytics.ZERO)}


def _wrapped(db: Session, user_id: uuid.UUID, year: int) -> dict:
    start, end = date(year, 1, 1), date(year, 12, 31)
    txns = db.query(Transaction).filter(*analytics.counted(user_id, start, end)).all()
    spends = [t for t in txns if t.kind == TransactionKind.spend]
    visits: dict[str, int] = {}
    for t in spends:
        if t.merchant_clean:
            visits[t.merchant_clean] = visits.get(t.merchant_clean, 0) + 1
    by_spend = analytics.top_merchants(db, user_id, start, end, 20)
    by_spend = [m for m in by_spend if m["key"] is not None]
    months = analytics.spend_summary(db, user_id, start, end, "month")["groups"]
    subscriptions = {s.key for s in db.query(RecurringSeries).filter(RecurringSeries.user_id == user_id)
                     if (s.user_type or s.type_guess) == "subscription" and s.user_status != "dismissed"}
    yoy = analytics.compare_periods(db, user_id, start, end, date(year - 1, 1, 1), date(year - 1, 12, 31))["rows"]
    biggest = max(yoy, key=lambda r: abs(r["delta"]), default=None)
    spend_by = {m["label"]: m["total"] for m in by_spend}
    # most visits; ties go to the merchant with more spend
    most_visits = max(visits.items(), key=lambda kv: (kv[1], spend_by.get(kv[0], 0))) if visits else None
    return {
        "top_merchant_by_visits": {"name": most_visits[0], "visits": most_visits[1]} if most_visits else None,
        "top_merchant_by_spend": {"name": by_spend[0]["label"], "amount": by_spend[0]["total"]} if by_spend else None,
        "most_expensive_month": ({"month": max(months, key=lambda m: m["total"])["key"][:7],
                                  "amount": max(months, key=lambda m: m["total"])["total"]} if months else None),
        "subscriptions_total": analytics.money(sum((t.amount for t in spends if series_key(t)[0] in subscriptions), analytics.ZERO)),
        "biggest_category_change": ({"category": biggest["label"], "this_year": biggest["a"], "last_year": biggest["b"],
                                     "change": biggest["delta"]} if biggest and biggest["delta"] else None),
        "transaction_count": len(txns),
        "savings_rate_pct": analytics.savings_rate(db, user_id, start, end)["rate_pct"],
    }


def build_report(db: Session, user_id: uuid.UUID, period_type: PeriodType, start: date) -> dict:
    start, end = period_for(period_type, start)
    prev_start, prev_end = previous_period(period_type, start)
    savings = analytics.savings_rate(db, user_id, start, end)
    prev_spend = analytics.spend_summary(db, user_id, prev_start, prev_end)["total"]
    spend = analytics.spend_summary(db, user_id, start, end)
    report = {
        "period": {"type": period_type, "start": start.isoformat(), "end": end.isoformat(), "label": label(period_type, start, end)},
        "totals": {"spend": savings["spend"], "income": savings["income"], "saved": savings["saved"],
                   "savings_rate_pct": savings["rate_pct"], "transactions": spend["count"]},
        "previous": {"start": prev_start.isoformat(), "end": prev_end.isoformat(), "spend": prev_spend,
                     "income": analytics.income_summary(db, user_id, prev_start, prev_end)["total"],
                     "spend_change": spend["total"] - prev_spend,
                     "spend_change_pct": ((spend["total"] - prev_spend) / prev_spend * 100).quantize(Decimal("0.1")) if prev_spend else None},
        "budget": analytics.budget_status(db, user_id, start if period_type == "monthly" else end) if period_type != "annual" else None,
        "top_categories": [{"name": g["label"], "amount": g["total"], "count": g["count"]} for g in spend["groups"][:TOP_N]],
        "top_merchants": [{"name": g["label"], "amount": g["total"], "count": g["count"]}
                          for g in analytics.top_merchants(db, user_id, start, end, TOP_N)],
        "recurring": _recurring_changes(db, user_id, start, end),
        "anomalies": _anomalies(db, user_id, period_type, start, end),
        "people": _people(db, user_id),
        "cash": {k: v for k, v in cash.wallet(db, user_id).items() if k in ("balance", "unaccounted", "spent", "withdrawn")},
        "safe_to_spend_next": _allowance(db, user_id, *next_period(period_type, end)) if period_type != "annual" else None,
    }
    if period_type == "monthly":
        report["goals"] = [{k: g[k] for k in ("name", "target_amount", "target_date", "saved", "remaining", "required_monthly",
                                                "status", "projected_date")} for g in analytics.goals_overview(db, user_id)]
    if period_type == "annual":
        report["wrapped"] = _wrapped(db, user_id, start.year)
    return json.loads(json.dumps(llm_safe(report)))   # plain JSON: Decimals → strings, nothing private


# ── Narrative ─────────────────────────────────────────────────────────────────

NARRATIVE_PROMPT = """Write a short summary of this personal finance report for its owner in India.
3 to 5 lines, then one line starting "Suggestion:" with one concrete, specific action.
Use only numbers that appear in the JSON, copied exactly (you may add Indian digit grouping and ₹).
Don't compute new figures (no sums, differences, averages or rounding). No investment, tax or credit advice."""

_NUMBER = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[Decimal]:
    out = set()
    for token in _NUMBER.findall(text):
        try:
            out.add(Decimal(token.replace(",", "")).normalize())
        except InvalidOperation:
            continue
    return out


def allowed_numbers(report: dict) -> set[Decimal]:
    """Every number in the report JSON, including date parts and absolute values."""
    nums = _numbers(json.dumps(report).replace("-", " "))
    return nums | {abs(n) for n in nums}


def narrative_is_grounded(text: str, report: dict) -> bool:
    allowed = allowed_numbers(report)
    return all(n in allowed or abs(n) in allowed for n in _numbers(text.replace("-", " ")))


def template_narrative(report: dict) -> str:
    t, p = report["totals"], report["previous"]
    lines = [f"{report['period']['label']}: you spent {inr(t['spend'])} and received {inr(t['income'])}."]
    if p["spend_change_pct"] is not None:
        direction = "more" if Decimal(p["spend_change"]) > 0 else "less"
        lines.append(f"That's {inr(abs(Decimal(p['spend_change'])))} {direction} than the previous period.")
    if report["top_categories"]:
        top = report["top_categories"][0]
        lines.append(f"Most went to {top['name']} ({inr(top['amount'])}).")
    if t["savings_rate_pct"] is not None:
        lines.append(f"You kept {t['savings_rate_pct']}% of your income.")
    over = [b for b in ((report.get("budget") or {}).get("categories") or []) if b["over"]]
    if over:
        lines.append(f"Suggestion: {over[0]['category']} is over budget by {inr(abs(Decimal(over[0]['remaining'])))}; review those payments first.")
    elif report["top_merchants"]:
        m = report["top_merchants"][0]
        lines.append(f"Suggestion: look at {m['name']}, your biggest merchant at {inr(m['amount'])}.")
    else:
        lines.append("Suggestion: import your latest statements so next period's report is complete.")
    return "\n".join(lines)


def write_narrative(report: dict) -> tuple[str, str]:
    """(text, source). Falls back to the template if the LLM fails or introduces a number."""
    try:
        reply = llm.complete([{"role": "system", "content": NARRATIVE_PROMPT},
                              {"role": "user", "content": json.dumps(report)}], temperature=0.3)
        text = (reply.get("content") or "").strip()
        if text and narrative_is_grounded(text, report):
            return text, "llm"
        logger.info("report narrative rejected: number not in report")
    except llm.LLMError as e:
        logger.warning(f"report narrative unavailable: {e}")
    return template_narrative(report), "template"


def generate(db: Session, user_id: uuid.UUID, period_type: PeriodType, day: date) -> tuple[Report, bool]:
    """Create the report for the period containing `day` unless it exists. Returns (report, created)."""
    start, end = period_for(period_type, day)
    existing = db.query(Report).filter(Report.user_id == user_id, Report.period_type == period_type,
                                       Report.period_start == start).first()
    if existing:
        return existing, False
    data = build_report(db, user_id, period_type, start)
    narrative, source = write_narrative(data)
    report = Report(user_id=user_id, period_type=period_type, period_start=start, period_end=end,
                    json=data, narrative=narrative, narrative_source=source)
    db.add(report)
    db.commit()
    return report, True


def last_complete(period_type: PeriodType, today: Optional[date] = None) -> date:
    """A day inside the most recent period that has fully ended."""
    today = today or clock.today()
    start, _ = period_for(period_type, today)
    return start - timedelta(days=1)
