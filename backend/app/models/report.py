"""Generated weekly / monthly / annual reports (services/reports.py). One per user, type and period."""

import uuid

from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    period_type = Column(String(10), nullable=False)      # weekly | monthly | annual
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    json = Column(JSON, nullable=False)                    # computed entirely by services/analytics.py
    narrative = Column(Text, nullable=False)
    narrative_source = Column(String(10), nullable=False)  # llm | template
    emailed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "period_type", "period_start", name="uq_reports_user_period"),)
