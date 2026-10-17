from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


# ── Import batch ──────────────────────────────────────────────────────────────
# Rows arrive already parsed and PII-stripped by the browser
# (frontend/src/import/pii.js). These checks are the server-side backstop.

MAX_BATCH_ROWS = 500
_ACCOUNT_LIKE = re.compile(r"\d{9,}")


def _no_account_numbers(value: str) -> str:
    if _ACCOUNT_LIKE.search(value):
        raise ValueError("contains a 9+ digit number (possible account number); strip it before sending")
    return value


class ImportRow(BaseModel):
    model_config = _STRICT

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?$")
    description_raw: str = Field(min_length=1, max_length=200)
    amount: str = Field(pattern=r"^\d{1,10}\.\d{2}$")
    direction: Literal["debit", "credit"]
    reference: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9/-]{3,40}$")
    source_type: Literal["bank_csv", "bank_pdf", "credit_card", "upi_google_pay", "upi_phonepe", "upi_paytm", "email_alert"]
    source_label: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9 ()&.,'/-]+$")
    type: Literal["transaction", "transfer"] = "transaction"
    # The browser's own merchant-model prediction (frontend/src/lib/merchantModel.js); the server checks the id
    predicted_subcategory: Optional[str] = Field(default=None, pattern=r"^[a-z_]+\.[a-z_]+$")
    predicted_confidence: Optional[float] = Field(default=None, ge=0, le=1)

    @field_validator("date")
    @classmethod
    def real_date(cls, v: str) -> str:
        parsed = datetime.fromisoformat(v)  # pattern already guarantees the shape
        if not (2000 <= parsed.year <= datetime.now().year + 1):
            raise ValueError("date out of range")
        return v

    @field_validator("amount")
    @classmethod
    def positive(cls, v: str) -> str:
        if Decimal(v) <= 0:
            raise ValueError("amount must be positive")
        return v

    @field_validator("description_raw", "source_label")
    @classmethod
    def no_account_numbers(cls, v: str) -> str:
        return _no_account_numbers(v)

    @field_validator("reference")
    @classmethod
    def reference_not_account_number(cls, v: Optional[str]) -> Optional[str]:
        # Same rule as cleanReference() in the browser: bare digit strings are
        # accepted only as cheque numbers (<= 8 digits) or 12-digit UTR/RRNs.
        if v is not None:
            digits = v.replace("/", "").replace("-", "")
            if digits.isdigit() and len(digits.lstrip("0")) not in (*range(9), 12):
                raise ValueError("reference looks like an account number")
        return v


class ImportBatch(BaseModel):
    model_config = _STRICT

    rows: List[ImportRow] = Field(min_length=1, max_length=MAX_BATCH_ROWS)


class ImportBatchResult(BaseModel):
    imported: int = 0
    duplicates_merged: int = 0
    transfers_flagged: int = 0
    rows_needing_review: int = 0
    failed: int = 0
