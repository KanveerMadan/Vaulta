from __future__ import annotations

import uuid
from typing import List, Literal, Optional

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=1000)
    session_id: Optional[uuid.UUID] = None


class ChatTable(BaseModel):
    title: str
    columns: List[str]
    rows: List[list]


class ChatActionCard(BaseModel):
    token: str
    tool: str
    summary: str
    expires_in_seconds: int


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    tables: List[ChatTable] = []
    actions: List[ChatActionCard] = []
    tools_used: List[str] = []


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=100)
    decision: Literal["confirm", "cancel"]


class ConfirmResponse(BaseModel):
    ok: bool
    message: str


class HistoryItem(BaseModel):
    role: str
    content: str


class Settings(BaseModel):
    ai_chat_enabled: bool
    timezone: str
    reports_weekly: bool
    reports_monthly: bool
    reports_annual: bool
    email_weekly: bool
    email_monthly: bool
    email_annual: bool
    email_configured: bool       # whether this server can send email at all


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    ai_chat_enabled: Optional[bool] = None
    timezone: Optional[str] = Field(default=None, max_length=64)
    reports_weekly: Optional[bool] = None
    reports_monthly: Optional[bool] = None
    reports_annual: Optional[bool] = None
    email_weekly: Optional[bool] = None
    email_monthly: Optional[bool] = None
    email_annual: Optional[bool] = None

    @field_validator("timezone")
    @classmethod
    def real_timezone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Unknown timezone; use an IANA name like Asia/Kolkata")
        return v
