"""
Every change a user makes to a transaction field (category, kind, ...).
A field with a correction is the user's: detection never overrides it.
Also the training data for learned rules (services/rules.py).
"""

import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Correction(Base):
    __tablename__ = "corrections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    field = Column(String(32), nullable=False)
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    __table_args__ = (
        Index("ix_corrections_transaction_field", "transaction_id", "field"),
        Index("ix_corrections_user", "user_id"),
    )
