"""
Re-categorisation runs (services/recategorise.py) and aggregate model metrics (services/model_metrics.py).
"""

import uuid

from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.crypto import EncryptedJSON
from app.core.database import Base


class RecategorisationRun(Base):
    """One applied re-categorisation, with every row's previous automatic values so it can be undone."""
    __tablename__ = "recategorisation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    reverted_at = Column(DateTime(timezone=True), nullable=True)
    changed = Column(Integer, nullable=False)
    # [{"id", "before": {...}, "after": {...}}]: automatic category, subcategory, merchant and explanation
    changes = Column(EncryptedJSON, nullable=False)
    summary = Column(JSON, nullable=False)          # {"Food & Dining → Groceries": n}: category names and counts only


class ModelMetric(Base):
    """Daily counts across all users, no user or merchant: how often each source categorised, and was corrected."""
    __tablename__ = "model_metrics"

    day = Column(Date, primary_key=True)
    source = Column(String(20), primary_key=True)     # model | known_merchant | personal | on_device
    categorised = Column(Integer, nullable=False, default=0, server_default=text("0"))
    corrected = Column(Integer, nullable=False, default=0, server_default=text("0"))
