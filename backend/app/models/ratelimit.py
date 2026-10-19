"""Shared rate-limit counters (app/core/ratelimit.py). One row per bucket; `bucket` is a keyed hash, never an IP or id."""

from sqlalchemy import Column, DateTime, Integer, String

from app.core.database import Base


class RateLimit(Base):
    __tablename__ = "rate_limits"

    bucket = Column(String(64), primary_key=True)
    hits = Column(Integer, nullable=False)
    reset_at = Column(DateTime(timezone=True), nullable=False, index=True)
