import uuid
import enum
from decimal import Decimal
from datetime import datetime

from sqlalchemy import (
    Column, String, Numeric, DateTime, ForeignKey,
    Enum as SAEnum, Index, UniqueConstraint, JSON, text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class TransactionSource(str, enum.Enum):
    gmail = "gmail"
    sms = "sms"
    csv = "csv"
    aa = "aa"  # Account Aggregator


class TransactionNature(str, enum.Enum):
    """
    Classifies *what kind* of money movement this transaction represents,
    independent of TransactionSource (which channel it was ingested from).
    See VAULTA master prompt, Section 5.
    """
    expense = "expense"
    income = "income"
    peer_payment_sent = "peer_payment_sent"
    peer_payment_received = "peer_payment_received"
    self_transfer = "self_transfer"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    source = Column(SAEnum(TransactionSource), nullable=False)

    # Raw string from the source (UPI: "Swiggy*ORDER123@ibl", email subject, etc.)
    merchant_raw = Column(String, nullable=False)
    # Normalized merchant name ("Swiggy") — from merchant normalizer
    merchant_clean = Column(String, nullable=True)
    # Category ("Food & Dining") — from normalizer or user override
    category = Column(String, nullable=True)

    # What kind of money movement this is (expense / income / peer payment / self-transfer).
    # Defaults to "expense" at the DB level for backfill safety — all rows ingested before
    # this field existed (CSV-only) were de facto merchant spending. New UPI-statement rows
    # must set this explicitly per the classification logic in upi_statement_parser.py;
    # do not rely on this default for anything written going forward.
    transaction_nature = Column(
        SAEnum(TransactionNature),
        nullable=False,
        server_default=TransactionNature.expense.value,
    )

    # DECIMAL, never FLOAT — money is exact
    amount = Column(Numeric(precision=12, scale=2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")

    transaction_date = Column(DateTime(timezone=True), nullable=False, index=True)

    # SHA256 of (source + raw_reference) — prevents duplicate inserts on re-sync
    idempotency_key = Column(String(64), nullable=False)

    # Original source payload preserved for re-derivation (email body, SMS text, CSV row)
    raw_source_data = Column(JSON, nullable=True)

    # Whether the user has manually corrected this transaction's merchant/category
    user_corrected = Column(String, nullable=True)  # stores original merchant_clean before correction

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="transactions")
    # All raw per-source evidence rows that contributed to (or were matched
    # against) this canonical transaction. See app/models/transaction_source.py
    # and Master Prompt Section 4. No cascade delete here on purpose — the FK
    # on the other side is ON DELETE SET NULL, so source evidence outlives the
    # canonical record it was merged into.
    source_records = relationship("TransactionSourceRecord", back_populates="transaction")

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_transaction_user_idempotency"),
        Index("ix_transactions_user_date", "user_id", "transaction_date"),
        Index("ix_transactions_user_category", "user_id", "category"),
        Index("ix_transactions_user_merchant", "user_id", "merchant_clean"),
        Index("ix_transactions_user_nature", "user_id", "transaction_nature"),
    )

    def __repr__(self) -> str:
        return f"<Transaction {self.id} | {self.merchant_clean} | ₹{self.amount} | {self.transaction_date.date()}>"


class Budget(Base):
    """
    Per-category monthly budget limits. Nullable category = overall monthly cap.
    Designed for Phase 4's alert system from the start — no retrofit needed.
    """
    __tablename__ = "budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # NULL category = total monthly budget; specific string = per-category limit
    category = Column(String, nullable=True)

    # Monthly limit in INR (DECIMAL, always)
    monthly_limit = Column(Numeric(precision=12, scale=2), nullable=False)

    # Soft-delete: deactivate instead of deleting so history is preserved
    is_active = Column(String, nullable=False, default="true")

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="budgets")

    __table_args__ = (
        # One active budget per category per user (NULL category = total budget)
        UniqueConstraint("user_id", "category", name="uq_budget_user_category"),
        Index("ix_budgets_user_active", "user_id", "is_active"),
    )

    def __repr__(self) -> str:
        cat = self.category or "TOTAL"
        return f"<Budget {self.id} | {cat} | ₹{self.monthly_limit}/mo>"