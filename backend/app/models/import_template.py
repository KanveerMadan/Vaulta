"""
Column-mapping templates for statement layouts the browser parsers don't
recognize. Keyed by a SHA-256 fingerprint of the statement's header row
(computed in the browser). Holds column indices and a date format only —
never header text or transaction data.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ImportTemplate(Base):
    __tablename__ = "import_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False)
    column_count = Column(Integer, nullable=False)
    source_type = Column(String, nullable=False)
    mapping = Column(JSON, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint", name="uq_import_template_user_fingerprint"),
    )


class Import(Base):
    """One statement upload (all its batches), so it can be deleted on its own (services/imports.py)."""
    __tablename__ = "imports"

    id = Column(UUID(as_uuid=True), primary_key=True)           # made by the browser, once per file
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(30), nullable=False)
    source_label = Column(String(60), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
