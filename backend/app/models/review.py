"""Review cards the user skipped, so they aren't asked again."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.crypto import Searchable
from app.core.database import Base


class ReviewDismissal(Base):
    __tablename__ = "review_dismissals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    card_id = Column(Searchable, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "card_id", name="uq_review_dismissals_user_card"),)
