from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.transaction import CATEGORIES

Tag = Literal["Rent", "Splits", "Family", "Friend", "Lent", "Other"]
DefaultKind = Literal["spend", "income", "transfer", "lent", "borrowed"]


class PersonResponse(BaseModel):
    id: uuid.UUID
    name: str
    masked_vpa: Optional[str]
    tag: Optional[str]
    default_category: Optional[str]
    default_kind: Optional[str]
    paid_total: Decimal
    received_total: Decimal
    transaction_count: int
    last_date: Optional[date]
    owed_to_you: Decimal
    you_owe: Decimal
    balance: Decimal              # > 0: they owe you; < 0: you owe them
    outstanding_days: Optional[int]


class PeopleList(BaseModel):
    people: List[PersonResponse]


class PersonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    tag: Optional[Tag] = None
    default_category: Optional[str] = None
    default_kind: Optional[DefaultKind] = None

    @field_validator("default_category")
    @classmethod
    def known_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in CATEGORIES:
            raise ValueError("Unknown category")
        return v

    @model_validator(mode="after")
    def something_to_change(self) -> "PersonUpdate":
        if not self.model_fields_set:
            raise ValueError("Nothing to update")
        if "display_name" in self.model_fields_set and self.display_name is None:
            raise ValueError("display_name can't be cleared")
        return self
