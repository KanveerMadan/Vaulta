from __future__ import annotations

import uuid
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.transaction import CATEGORIES

_KINDS = {"spend", "income", "transfer", "refund", "reversal", "lent", "borrowed", "repayment"}


class RuleResponse(BaseModel):
    id: uuid.UUID
    merchant_key: str
    merchant: str
    field: str
    value: str
    origin: str
    matches: int          # transactions from this merchant


class RuleList(BaseModel):
    rules: List[RuleResponse]


def check_rule_value(field: str, value: str) -> None:
    if field == "category" and value not in CATEGORIES:
        raise ValueError("Unknown category")
    if field == "kind" and value not in _KINDS:
        raise ValueError("Unknown kind")


class RuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    merchant_key: str = Field(min_length=1, max_length=100)
    merchant: str = Field(min_length=1, max_length=100)
    field: Literal["category", "kind"]
    value: str = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def valid_value(self) -> "RuleCreate":
        check_rule_value(self.field, self.value)
        return self


class RuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: str = Field(min_length=1, max_length=40)
