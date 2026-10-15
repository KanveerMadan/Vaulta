"""
Things worth a second look (services/anomalies.py): possible duplicate
charges, unusual amounts, category spikes, failed UPI debits never reversed.
Re-detected on every detection run; the user's dismissal persists by key.
"""

import uuid

from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Anomaly(Base):
    __tablename__ = "anomalies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(160), nullable=False)       # stable identity of the finding, e.g. "unusual:<txn id>"
    type = Column(String(30), nullable=False)       # duplicate_charge | unusual_amount | category_spike | unreversed_failed_upi
    occurred_on = Column(Date, nullable=False)      # date of the transaction / first day of the spiking month
    details = Column(JSON, nullable=False)          # merchant/category labels, amounts, dates, transaction ids
    status = Column(String(10), nullable=False, default="open")   # open | dismissed
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_anomalies_user_key"),)
