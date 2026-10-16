"""Telegram: one-time link codes and quick-add entries waiting for ✓."""

import uuid

from sqlalchemy import BigInteger, JSON, Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.crypto import EncryptedJSON
from app.core.database import Base


class TelegramLinkCode(Base):
    __tablename__ = "telegram_link_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)


class TelegramEntry(Base):
    """An expense parsed from a Telegram message. Saved only when the user taps ✓ Save."""
    __tablename__ = "telegram_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    payload = Column(EncryptedJSON, nullable=False)                # the parsed entry (amount, merchant, category, date, …)
    status = Column(String(10), nullable=False, default="pending")   # pending | saved | cancelled | undone
    transaction_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    saved_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_telegram_entries_user_saved", "user_id", "saved_at"),)
