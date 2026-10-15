"""Budgets: create/reactivate, and suggestions from recent spending."""

from __future__ import annotations

import math
import uuid
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
from statistics import median
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import clock
from app.models.transaction import Budget, Transaction
from app.models.user import User
from app.services.recurring import add_months
from app.services.transaction_service import _build_spend_rows

# ── Tunable thresholds (listed in the Phase 2 report) ─────────────────────────
SUGGESTION_MONTHS = 3          # full months of history needed, and the median window
SUGGESTION_ROUND_TO = 100      # round the suggested limit up to this many rupees


def create_or_reactivate(db: Session, user: User, category: Optional[str], monthly_limit) -> Optional[Budget]:
    """
    New active budget for the category, reusing the most recent deleted row
    if there is one. None if an active budget already exists.
    """
    same_category = Budget.category.is_(None) if category is None else Budget.category == category
    rows = (
        db.query(Budget)
        .filter(Budget.user_id == user.id, same_category)
        .order_by(Budget.updated_at.desc())
        .all()
    )
    if any(b.is_active for b in rows):
        return None
    budget = rows[0] if rows else Budget(id=uuid.uuid4(), user_id=user.id, category=category)
    budget.monthly_limit = monthly_limit
    budget.is_active = True
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget



def suggest_budgets(db: Session, user: User, today: Optional[date] = None) -> list[tuple[str, Decimal, list[Decimal]]]:
    """
    [(category, suggested limit, the monthly totals it came from)] for
    categories without an active budget, once the user has SUGGESTION_MONTHS
    full months of history. Limit = median monthly net spend, rounded up.
    """
    today = today or clock.today()
    first_of_this_month = today.replace(day=1)
    window_start = add_months(first_of_this_month, -SUGGESTION_MONTHS)
    earliest = db.query(func.min(Transaction.transaction_date)).filter(Transaction.user_id == user.id).scalar()
    # History has to reach into the first month of the window
    if earliest is None or earliest.date() >= add_months(window_start, 1):
        return []
    budgeted = {b.category for b in db.query(Budget).filter(Budget.user_id == user.id, Budget.is_active.is_(True))}
    per_month: dict[str, list[Decimal]] = {}
    for i in range(SUGGESTION_MONTHS):
        start = add_months(window_start, i)
        end_day = monthrange(start.year, start.month)[1]
        rows = _build_spend_rows(
            db, user.id,
            datetime(start.year, start.month, 1, tzinfo=timezone.utc),
            datetime(start.year, start.month, end_day, 23, 59, 59, tzinfo=timezone.utc),
        )
        for r in rows:
            if r.category:
                per_month.setdefault(r.category, [Decimal("0")] * SUGGESTION_MONTHS)[i] = r.total or Decimal("0")
    out = []
    for category, totals in sorted(per_month.items()):
        mid = Decimal(median(totals))
        if category in budgeted or mid <= 0:
            continue
        limit = Decimal(math.ceil(mid / SUGGESTION_ROUND_TO) * SUGGESTION_ROUND_TO)
        out.append((category, limit, totals))
    return out
