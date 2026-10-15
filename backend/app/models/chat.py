"""
Chat: visible conversation history (last 10 turns per session, purged after
30 days) and actions the assistant proposed, awaiting the user's confirmation.
"""

import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    role = Column(String(10), nullable=False)          # user | assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    __table_args__ = (
        Index("ix_chat_messages_user_session", "user_id", "session_id", "created_at"),
        Index("ix_chat_messages_created_at", "created_at"),
    )


class ChatAction(Base):
    """A write the assistant proposed. Executes only via /api/chat/confirm with its token."""
    __tablename__ = "chat_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)   # sha256 of the token; the token itself is never stored
    tool = Column(String(40), nullable=False)
    args = Column(JSON, nullable=False)                              # resolved, validated arguments
    summary = Column(String(300), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    outcome = Column(String(10), nullable=True)                      # confirmed | cancelled
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
