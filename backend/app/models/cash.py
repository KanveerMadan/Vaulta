"""Cash wallet declarations: "I have ₹X in cash now" (the wallet's baseline)."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class CashDeclaration(Base):
    __tablename__ = "cash_declarations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    reason = Column(String(12), nullable=False)          # declared | still_have
    declared_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
