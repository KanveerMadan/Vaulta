"""
The user's own subcategories (inside a taxonomy group) and tags.

Tags are many-to-many labels ("Goa trip", "Reimbursable") that sit across categories: a transaction keeps its category
and can carry any number of tags. Names are the user's words, so they are encrypted; Searchable keeps them unique.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID

from app.core.crypto import Searchable
from app.core.database import Base


class CustomSubcategory(Base):
    __tablename__ = "custom_subcategories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    group = Column(String, nullable=False)          # a taxonomy group name ("Food & Dining")
    name = Column(Searchable, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "group", "name", name="uq_custom_subcategories_user_group_name"),)

    @property
    def key(self) -> str:
        return f"custom:{self.id}"


class Tag(Base):
    __tablename__ = "tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(Searchable, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tags_user_name"),)


class TransactionTag(Base):
    __tablename__ = "transaction_tags"

    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
