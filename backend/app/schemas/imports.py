from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Must match DATE_FORMATS in frontend/src/import/mapping.js
DateFormat = Literal[
    "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y",
    "%d %b %Y", "%d-%b-%Y", "%d %b %y", "%d-%b-%y", "%d %b, %Y",
    "%Y-%m-%d", "%m/%d/%Y",
]

ColumnIndex = Optional[int]
_STRICT = ConfigDict(extra="forbid", strict=True)


class ColumnMapping(BaseModel):
    model_config = _STRICT

    date: int = Field(ge=0, le=99)
    description: int = Field(ge=0, le=99)
    debit: ColumnIndex = Field(default=None, ge=0, le=99)
    credit: ColumnIndex = Field(default=None, ge=0, le=99)
    amount: ColumnIndex = Field(default=None, ge=0, le=99)
    reference: ColumnIndex = Field(default=None, ge=0, le=99)
    date_format: DateFormat
    amount_sign: Literal["negative_is_debit", "negative_is_credit"] = "negative_is_debit"

    @model_validator(mode="after")
    def needs_an_amount_column(self) -> "ColumnMapping":
        if self.debit is None and self.credit is None and self.amount is None:
            raise ValueError("Map a debit/credit column pair or a single amount column")
        return self


class ImportTemplateUpsert(BaseModel):
    model_config = _STRICT

    column_count: int = Field(ge=1, le=100)
    source_type: Literal["bank_csv", "bank_pdf"]
    mapping: ColumnMapping


class ImportTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fingerprint: str
    column_count: int
    source_type: str
    mapping: ColumnMapping
    updated_at: datetime
