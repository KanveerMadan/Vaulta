"""
User rules: merchant → category or kind. Learned from repeated corrections
(services/rules.py), created from review answers, or edited on the Rules
page. Applied by services/detection.py after transfer/refund detection.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.crypto import Encrypted, Searchable
from app.core.database import Base


class Rule(Base):
    __tablename__ = "rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant_key = Column(Searchable, nullable=False)   # services/keys.py merchant_key()
    merchant_label = Column(Encrypted, nullable=False)  # for display ("Swiggy")
    field = Column(String(16), nullable=False)            # category | kind
    value = Column(String, nullable=False)
    origin = Column(String(10), nullable=False)           # learned | review | manual

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "merchant_key", "field", name="uq_rules_user_merchant_field"),)
