from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from app.models.transaction import TransactionKind, TransactionSource, TransactionNature
from app.services.merchant_normalizer import _PATTERNS

# Every category the normalizer can assign, plus the ones set by nature or
# by hand. frontend/src/lib/categories.js lists the same names.
CATEGORIES = frozenset({category for _, _, category, _ in _PATTERNS}) | {
    "Sent to People", "Received from People", "Transfers", "Cash", "Other",
}


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
    notes: Optional[str] = None
    direction: Literal["debit", "credit"]
    kind: TransactionKind
    transfer_group_id: Optional[uuid.UUID] = None
    refund_of_id: Optional[uuid.UUID] = None
    person_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


def _known_category(v: Optional[str]) -> Optional[str]:
    if v is not None and v not in CATEGORIES:
        raise ValueError(f"Unknown category. Use one of: {', '.join(sorted(CATEGORIES))}")
    return v


class ManualTransactionCreate(BaseModel):
    """Manual entry. client_id makes retries of the same submit idempotent."""
    model_config = ConfigDict(extra="forbid", strict=True)

    client_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    amount: str = Field(pattern=r"^\d{1,10}(\.\d{1,2})?$")
    direction: Literal["debit", "credit"] = "debit"
    merchant: str = Field(min_length=1, max_length=100)
    category: Optional[str] = None
    payment_method: Literal["cash", "online"] = "cash"
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("category")
    @classmethod
    def known_category(cls, v: Optional[str]) -> Optional[str]:
        return _known_category(v)

    @field_validator("date")
    @classmethod
    def real_date(cls, v: str) -> str:
        datetime.fromisoformat(v)
        return v

    @field_validator("amount")
    @classmethod
    def positive(cls, v: str) -> str:
        if Decimal(v) <= 0:
            raise ValueError("amount must be positive")
        return v

    @field_validator("merchant", "notes")
    @classmethod
    def no_account_numbers(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and re.search(r"\d{9,}", v):
            raise ValueError("contains a 9+ digit number (possible account number)")
        return v.strip() if v is not None else v


Kind = Literal["spend", "income", "transfer", "refund", "reversal", "lent", "borrowed", "repayment"]


class TransactionUpdate(BaseModel):
    """PATCH body. Send only the fields to change; category null clears it."""
    model_config = ConfigDict(extra="forbid", strict=True)

    category: Optional[str] = None
    kind: Optional[Kind] = None
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("category")
    @classmethod
    def known_category(cls, v: Optional[str]) -> Optional[str]:
        return _known_category(v)

    @model_validator(mode="after")
    def something_to_change(self) -> "TransactionUpdate":
        if not self.model_fields_set:
            raise ValueError("Nothing to update")
        if "kind" in self.model_fields_set and self.kind is None:
            raise ValueError("kind can't be cleared")
        return self


class TransactionListResponse(BaseModel):
    items: List[TransactionResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


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
    period_start: datetime
    period_end: datetime
    period: str = "month"  # "month" | "year" | "lifetime"

    total_spend: Decimal
    total_received: Decimal
    net_cash_flow: Decimal

    transaction_count: int
    total_budget: Optional[Decimal] = None
    days_remaining: Optional[int] = None
    avg_monthly_spend: Optional[Decimal] = None  # year/lifetime only

    categories: List[CategorySummary]
    top_merchants: List[dict]

    mom_total_delta: Optional[Decimal] = None
    mom_total_delta_pct: Optional[Decimal] = None
