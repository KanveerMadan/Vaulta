"""
People the user pays or gets paid by over UPI (P2P), detected from masked
UPI IDs / names in narrations (services/keys.py). Keyed by a hash of the
masked identifier + name token; the user can rename and tag them.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Person(Base):
    __tablename__ = "people"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key_hash = Column(String(64), nullable=False)
    display_name = Column(String(100), nullable=False)
    masked_vpa = Column(String(80), nullable=True)
    tag = Column(String(20), nullable=True)               # Rent | Splits | Family | Friend | Lent | Other
    default_category = Column(String, nullable=True)
    default_kind = Column(String(12), nullable=True)
    # Set when this person was merged into another (auto or by the user); their
    # transactions then point at the surviving person
    merged_into_id = Column(UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "key_hash", name="uq_people_user_key"),)
