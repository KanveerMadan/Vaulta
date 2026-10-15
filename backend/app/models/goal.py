"""Savings goals and the money put towards them (entries are not transactions)."""

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Goal(Base):
    __tablename__ = "goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    target_amount = Column(Numeric(12, 2), nullable=False)
    target_date = Column(Date, nullable=False)
    category = Column(String(50), nullable=True)      # optional spending category to cut
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    entries = relationship("GoalEntry", back_populates="goal", cascade="all, delete-orphan", order_by="GoalEntry.entry_date")


class GoalEntry(Base):
    """"I put ₹5,000 towards the laptop." Negative amounts take money back out."""
    __tablename__ = "goal_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id = Column(UUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    entry_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    goal = relationship("Goal", back_populates="entries")
