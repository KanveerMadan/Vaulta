from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, field_validator, ConfigDict


class BudgetCreate(BaseModel):
    # NULL category = total monthly budget cap
    # Specific string = per-category limit (must match category names from transactions)
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
    category: Optional[str] = None  # None = overall monthly budget
    monthly_limit: Decimal
    is_active: str
    created_at: datetime
    updated_at: datetime


class BudgetListResponse(BaseModel):
    items: List[BudgetResponse]
    total_monthly_limit: Optional[Decimal] = None  # Sum of all active per-category limits