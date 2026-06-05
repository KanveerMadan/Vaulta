from sqlalchemy import Column, String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firebase_uid = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=True)

    # Onboarding state — tracks which data sources are connected
    gmail_connected = Column(Boolean, default=False)
    sms_connected = Column(Boolean, default=False)
    aa_connected = Column(Boolean, default=False)        # Account Aggregator (Phase 5)

    # Gmail OAuth tokens (encrypted at rest — Phase 1)
    gmail_access_token = Column(String, nullable=True)
    gmail_refresh_token = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<User {self.email}>"