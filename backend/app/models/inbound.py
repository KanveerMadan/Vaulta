"""
Inbound bank-alert email: metadata only. No email content is ever stored —
the normalized row goes through the import pipeline; here we keep what
happened (for the Connect page counts) and Gmail's forwarding confirmation
link/code (shown to the user, never clicked by us).
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class InboundEvent(Base):
    __tablename__ = "inbound_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    bank_key = Column(String(20), nullable=True)
    bank_name = Column(String(60), nullable=True)
    # parsed | unparsed | not_transaction | untrusted_sender | auth_failed | gmail_confirmation
    outcome = Column(String(20), nullable=False)

    __table_args__ = (Index("ix_inbound_events_user_received", "user_id", "received_at"),)


class GmailConfirmation(Base):
    __tablename__ = "gmail_confirmations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    link = Column(String(500), nullable=True)
    code = Column(String(20), nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
