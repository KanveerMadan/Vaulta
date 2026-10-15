"""Proactive alerts (services/alerts.py). Stored once per dedup key; delivery state per channel."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(30), nullable=False)
    key = Column(String(200), nullable=False)          # type + subject + period, e.g. "budget_threshold:Food & Dining:2024-06:80"
    message = Column(String(500), nullable=False)      # merchant labels and amounts only, never narrations
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    telegram_status = Column(String(10), nullable=True)   # queued (quiet hours / retry) | sent; null = not for Telegram
    email_sent_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_alerts_user_key"),)
