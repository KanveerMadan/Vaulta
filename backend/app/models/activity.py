"""
Account activity the user can review in Settings → Activity: sign-ins, exports, deletions, Telegram link/unlink,
forwarding address regenerated, settings changes. `detail` holds names only (which settings, what was deleted),
never values.
"""

import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ActivityEvent(Base):
    __tablename__ = "activity_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(30), nullable=False)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    __table_args__ = (Index("ix_activity_log_user_created", "user_id", "created_at"),)
