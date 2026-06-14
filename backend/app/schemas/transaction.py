from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, field_validator, ConfigDict

from app.models.transaction import TransactionSource


# ─────────────────────────────────────────────
# Transaction schemas
# ─────────────────────────────────────────────

class TransactionBase(BaseModel):
    merchant_raw: str
    merchant_clean: Optional[str] = None
    category: Optional[str] = None
    amount: Decimal
    currency: str = "INR"
    transaction_date: datetime
    source: TransactionSource

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Transaction amount must be positive")
        return v

    @field_validator("currency")
    @classmethod
    def currency_must_be_iso(cls, v: str) -> str:
        if len(v) != 3:
            raise ValueError("Currency must be a 3-character ISO 4217 code")
        return v.upper()


class TransactionCreate(TransactionBase):
    idempotency_key: str
    raw_source_data: Optional[dict] = None


class TransactionResponse(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    idempotency_key: str
    user_corrected: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TransactionListResponse(BaseModel):
    items: List[TransactionResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


# ─────────────────────────────────────────────
# Summary schemas
# ─────────────────────────────────────────────

class CategorySummary(BaseModel):
    category: str
    total: Decimal
    transaction_count: int
    percentage_of_spend: Decimal
    # Per-category budget limit (null if no budget set for this category)
    budget_limit: Optional[Decimal] = None
    # Percentage of budget consumed (null if no budget set)
    budget_consumed_pct: Optional[Decimal] = None
    # Month-over-month delta: positive = spent more, negative = spent less
    mom_delta: Optional[Decimal] = None
    mom_delta_pct: Optional[Decimal] = None


class MonthlySummary(BaseModel):
    """
    Summary for a given month. Shape is final — wired to Dashboard.jsx MetricCards.
    budget_* fields come from the budgets table (per-category), aggregated here.
    """
    period_start: datetime
    period_end: datetime
    total_spend: Decimal
    transaction_count: int

    # Overall budget = sum of active per-category budget limits, or null if none set
    total_budget: Optional[Decimal] = None
    # Days remaining in current period (used by Dashboard countdown)
    days_remaining: int

    # Category breakdown — each entry carries its own budget_limit
    categories: List[CategorySummary]

    # Top merchants by spend this month
    top_merchants: List[dict]  # [{merchant_clean, total, count}]

    # Month-over-month total delta
    mom_total_delta: Optional[Decimal] = None
    mom_total_delta_pct: Optional[Decimal] = None


# ─────────────────────────────────────────────
# Budget schemas
# ─────────────────────────────────────────────

class BudgetCreate(BaseModel):
    # NULL category = total monthly budget
    category: Optional[str] = None
    monthly_limit: Decimal

    @field_validator("monthly_limit")
    @classmethod
    def limit_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Budget limit must be positive")
        return v


class BudgetUpdate(BaseModel):
    monthly_limit: Decimal

    @field_validator("monthly_limit")
    @classmethod
    def limit_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Budget limit must be positive")
        return v


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    category: Optional[str] = None
    monthly_limit: Decimal
    is_active: str
    created_at: datetime
    updated_at: datetime