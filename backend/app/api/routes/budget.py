"""
Budget routes — Phase 1

Lets users set per-category monthly limits (and an optional overall cap).
These feed directly into MonthlySummary.categories[].budget_consumed_pct
and Dashboard.jsx's progress bars.

Design decisions (from Section 6, Decision Required #2):
  - Per-category budgets table, not a single User.monthly_budget column
  - category=None means the overall monthly cap (one allowed per user)
  - Phase 4's budget alerts are built on top of this exact structure
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.transaction import Budget
from app.models.user import User
from app.schemas.budget import BudgetCreate, BudgetUpdate, BudgetResponse, BudgetListResponse

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def _get_budget_or_404(db: Session, budget_id: uuid.UUID, user: User) -> Budget:
    """Fetch a budget scoped to the current user — 404 if not found or not owned."""
    budget = (
        db.query(Budget)
        .filter(Budget.id == budget_id, Budget.user_id == user.id)
        .first()
    )
    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found.",
        )
    return budget


@router.get("", response_model=BudgetListResponse)
def list_budgets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all active budgets for the authenticated user."""
    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == current_user.id, Budget.is_active == "true")
        .order_by(Budget.category.nullsfirst())
        .all()
    )

    # Sum of per-category limits (excludes the overall cap if set)
    category_budgets = [b for b in budgets if b.category is not None]
    total = sum(b.monthly_limit for b in category_budgets) if category_budgets else None

    return BudgetListResponse(
        items=[BudgetResponse.model_validate(b) for b in budgets],
        total_monthly_limit=total,
    )


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
def create_budget(
    payload: BudgetCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a budget limit.

    - `category: null` sets the overall monthly cap.
    - `category: "Food & Dining"` sets a per-category limit.
    - Only one active budget per category per user (unique constraint enforced at DB level).
    """
    # Check for existing active budget for this category
    existing = (
        db.query(Budget)
        .filter(
            Budget.user_id == current_user.id,
            Budget.category == payload.category,
            Budget.is_active == "true",
        )
        .first()
    )
    if existing:
        category_label = payload.category or "overall"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An active budget for '{category_label}' already exists. Use PATCH to update it.",
        )

    budget = Budget(
        id=uuid.uuid4(),
        user_id=current_user.id,
        category=payload.category,
        monthly_limit=payload.monthly_limit,
        is_active="true",
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return BudgetResponse.model_validate(budget)


@router.patch("/{budget_id}", response_model=BudgetResponse)
def update_budget(
    budget_id: uuid.UUID,
    payload: BudgetUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the monthly limit for an existing budget."""
    budget = _get_budget_or_404(db, budget_id, current_user)
    budget.monthly_limit = payload.monthly_limit
    db.commit()
    db.refresh(budget)
    return BudgetResponse.model_validate(budget)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    budget_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Soft-delete a budget (sets is_active=false).
    Hard deletion is intentionally avoided — preserves history for Phase 5's
    Financial Health Score, which needs to know when budgets were active.
    """
    budget = _get_budget_or_404(db, budget_id, current_user)
    budget.is_active = "false"
    db.commit()