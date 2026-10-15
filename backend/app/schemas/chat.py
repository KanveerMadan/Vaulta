from __future__ import annotations

import uuid
from typing import Dict, List, Literal, Optional

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
    read_only: bool = False          # demo: shown, but confirming is refused
    note: Optional[str] = None


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
    alert_channels: Dict[str, Dict[str, bool]]   # {type: {"telegram": bool, "email": bool}}, defaults filled in
    quiet_start: int
    quiet_end: int


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
    alert_channels: Optional[Dict[str, Dict[str, bool]]] = None   # partial: only the types/channels given change
    quiet_start: Optional[int] = Field(default=None, ge=0, le=23)
    quiet_end: Optional[int] = Field(default=None, ge=0, le=23)

    @field_validator("alert_channels")
    @classmethod
    def known_alerts(cls, v):
        from app.services.alerts import TYPES
        for kind, chans in (v or {}).items():
            if kind not in TYPES or not set(chans) <= {"telegram", "email"}:
                raise ValueError(f"alert types: {', '.join(TYPES)}; channels: telegram, email")
        return v

    @field_validator("timezone")
    @classmethod
    def real_timezone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Unknown timezone; use an IANA name like Asia/Kolkata")
        return v
