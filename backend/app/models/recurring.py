"""
Recurring payment series, detected from the user's spend history
(services/recurring.py). Detected fields are rewritten on every detection
run; user_* fields (confirm/dismiss, rename, retype, keep/review) persist.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class RecurringSeries(Base):
    __tablename__ = "recurring_series"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # "merchant:<merchant key>" or "person:<person key>"
    key = Column(String(100), nullable=False)

    # Detected
    display_name = Column(String(100), nullable=False)
    cadence = Column(String(10), nullable=False)          # weekly | monthly | yearly
    typical_amount = Column(Numeric(12, 2), nullable=False)
    last_amount = Column(Numeric(12, 2), nullable=False)
    last_date = Column(Date, nullable=False)
    next_expected = Column(Date, nullable=False)
    occurrences = Column(Integer, nullable=False)
    status = Column(String(10), nullable=False)           # active | missed | cancelled
    type_guess = Column(String(15), nullable=False)       # subscription | rent | emi | sip | bill | other
    previous_amount = Column(Numeric(12, 2), nullable=True)  # set when the price changed > 5%
    category = Column(String, nullable=True)

    # The user's
    user_status = Column(String(10), nullable=True)       # confirmed | dismissed
    user_name = Column(String(100), nullable=True)
    user_type = Column(String(15), nullable=True)
    usage = Column(String(10), nullable=True)             # keep | review

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_recurring_user_key"),)
