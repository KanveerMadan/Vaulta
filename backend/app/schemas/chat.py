from __future__ import annotations

import uuid
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    ai_chat_enabled: Optional[bool] = None
