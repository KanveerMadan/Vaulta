"""A deleted account whose Firebase login is still to be deleted (services/deletion.py, alembic e3f9a5b7c8d0)."""

import uuid

from sqlalchemy import Column, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class PendingAuthDeletion(Base):
    __tablename__ = "pending_auth_deletions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firebase_uid = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=True)            # for the confirmation email; gone when the deletion completes
    requested_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    attempts = Column(Integer, nullable=False, server_default="0", default=0)
    last_error = Column(String(80), nullable=True)
