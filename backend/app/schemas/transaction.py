from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, field_validator, ConfigDict

from app.models.transaction import TransactionSource, TransactionNature


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
    transaction_nature: TransactionNature = TransactionNature.expense

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
    budget_limit: Optional[Decimal] = None
    budget_consumed_pct: Optional[Decimal] = None
    mom_delta: Optional[Decimal] = None
    mom_delta_pct: Optional[Decimal] = None


class MonthlySummary(BaseModel):
    """
    Summary for a given month. Wired to Dashboard.jsx MetricCards.

    total_spend    — expense + peer_payment_sent rows only (money that genuinely
                     left the user's hand, Section 5).
    total_received — income + peer_payment_received rows (money that arrived).
    net_cash_flow  — total_received - total_spend.
    self_transfer rows are excluded from all three figures.
    """
    period_start: datetime
    period_end: datetime

    total_spend: Decimal
    total_received: Decimal
    net_cash_flow: Decimal

    transaction_count: int
    total_budget: Optional[Decimal] = None
    days_remaining: int

    categories: List[CategorySummary]
    top_merchants: List[dict]  # [{merchant_clean, total, count}]

    mom_total_delta: Optional[Decimal] = None
    mom_total_delta_pct: Optional[Decimal] = None


# ─────────────────────────────────────────────
# Budget schemas
# ─────────────────────────────────────────────

class BudgetCreate(BaseModel):
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