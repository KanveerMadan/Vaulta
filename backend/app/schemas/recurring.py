from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

SeriesType = Literal["subscription", "rent", "emi", "sip", "bill", "other"]


class RecurringSeriesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    cadence: str
    typical_amount: Decimal
    monthly_amount: Decimal
    last_amount: Decimal
    last_date: date
    next_expected: date
    occurrences: int
    status: str
    type: str
    category: Optional[str]
    price_change: Optional[dict]   # {"old": ..., "new": ...} when the price moved > 5%
    user_status: Optional[str]
    usage: Optional[str]


class RecurringOverview(BaseModel):
    series: List[RecurringSeriesResponse]
    monthly_committed: Decimal
    upcoming: List[RecurringSeriesResponse]   # due in the next 14 days


class RecurringUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    user_status: Optional[Literal["confirmed", "dismissed"]] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    type: Optional[SeriesType] = None
    usage: Optional[Literal["keep", "review"]] = None

    @model_validator(mode="after")
    def something_to_change(self) -> "RecurringUpdate":
        if not self.model_fields_set:
            raise ValueError("Nothing to update")
        return self
