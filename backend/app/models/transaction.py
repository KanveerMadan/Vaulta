import uuid
import enum
from decimal import Decimal
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, String, Numeric, DateTime, ForeignKey, func,
    Enum as SAEnum, Index, UniqueConstraint, JSON, text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import object_session, relationship

from app.core.crypto import Encrypted, EncryptedJSON, Searchable
from app.core.database import Base
from app.models.transaction_source import TransactionDirection


class TransactionSource(str, enum.Enum):
    gmail = "gmail"
    sms = "sms"
    csv = "csv"
    aa = "aa"  # Account Aggregator
    manual = "manual"


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


class TransactionKind(str, enum.Enum):
    """
    What a transaction means for the user's numbers. Only `spend` (net of
    `refund`) counts as spending and only `income` as income; everything else
    is excluded from totals. Set by default from direction at import, then
    recomputed by services/detection.py unless the user corrected it.
    """
    spend = "spend"
    income = "income"
    transfer = "transfer"      # between the user's own accounts / card bill
    refund = "refund"          # money back from a merchant (credit)
    reversal = "reversal"      # failed UPI debit and its reversal credit
    lent = "lent"              # money given to a person, to be paid back
    borrowed = "borrowed"      # money received from a person, to pay back
    repayment = "repayment"    # settles lent/borrowed


# Which directions each kind can have (enforced on PATCH)
KIND_DIRECTIONS = {
    TransactionKind.spend: {"debit"},
    TransactionKind.income: {"credit"},
    TransactionKind.refund: {"credit"},
    TransactionKind.lent: {"debit"},
    TransactionKind.borrowed: {"credit"},
    TransactionKind.transfer: {"debit", "credit"},
    TransactionKind.reversal: {"debit", "credit"},
    TransactionKind.repayment: {"debit", "credit"},
}


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    source = Column(SAEnum(TransactionSource), nullable=False)

    # Raw string from the source (UPI: "Swiggy*ORDER123@ibl", email subject, etc.)
    merchant_raw = Column(Encrypted, nullable=False)
    # Normalized merchant name ("Swiggy") — from merchant normalizer
    merchant_clean = Column(Searchable, nullable=True)
    # Effective category ("Food & Dining"): auto_category unless the user
    # corrected it or detection overrode it (e.g. a refund takes its original's)
    category = Column(String, nullable=True)
    # What the system assigned at import (normalizer / nature); detection
    # resets `category` to this before re-applying its own overrides
    auto_category = Column(String, nullable=True)
    # Optional second level (services/taxonomy.py): a taxonomy id ("food.delivery") or "custom:<uuid>". Always inside
    # `category`'s group. auto_subcategory is what the system assigned, like auto_category.
    subcategory = Column(String(64), nullable=True)
    auto_subcategory = Column(String(64), nullable=True)

    # What kind of money movement this is (expense / income / peer payment / self-transfer).
    # Defaults to "expense" at the DB level for backfill safety — all rows ingested before
    # this field existed (CSV-only) were de facto merchant spending. New UPI-statement rows
    # must set this explicitly (see transaction_service.import_rows);
    # do not rely on this default for anything written going forward.
    transaction_nature = Column(
        SAEnum(TransactionNature),
        nullable=False,
        server_default=TransactionNature.expense.value,
    )

    # Money out (debit) or in (credit), as the source stated it
    direction = Column(SAEnum(TransactionDirection), nullable=False)
    kind = Column(SAEnum(TransactionKind), nullable=False)
    # Both legs of a detected own-account transfer share this id
    transfer_group_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    # The individual this P2P transaction is with (services/keys.py)
    person_id = Column(UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True, index=True)
    # Cash wallet movement (services/cash.py, set by detection):
    # withdrawal (ATM → wallet) | spend (cash paid out) | received (cash in)
    cash_flow = Column(String(10), nullable=True)
    # Split: the parent stays (is_split) but is excluded from totals; its
    # children (split_parent_id) carry the parts and count instead
    is_split = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    split_parent_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True, index=True)
    # Refund/reversal credit → the debit it gives money back for
    refund_of_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True)

    # DECIMAL, never FLOAT — money is exact
    amount = Column(Numeric(precision=12, scale=2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")

    transaction_date = Column(DateTime(timezone=True), nullable=False, index=True)

    # SHA256 of (source + raw_reference) — prevents duplicate inserts on re-sync
    idempotency_key = Column(String(64), nullable=False)

    # Original source payload preserved for re-derivation (email body, SMS text, CSV row)
    raw_source_data = Column(EncryptedJSON, nullable=True)

    # "true" once the user has edited the category/notes (string flag kept for API compatibility)
    user_corrected = Column(String, nullable=True)

    # Free-text note from the user
    notes = Column(Encrypted, nullable=True)

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
    splits = relationship(
        "Transaction", foreign_keys=[split_parent_id], order_by="Transaction.amount.desc()",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    @property
    def tags(self) -> list[str]:
        """Tag names (models/category.py). Lists prefetch them into _tags (transaction_service.get_transactions)."""
        if "_tags" not in self.__dict__:
            from app.services.categories import tag_names_for
            self._tags = tag_names_for(object_session(self), self.user_id, [self.id]).get(self.id, [])
        return self._tags

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_transaction_user_idempotency"),
        Index("ix_transactions_user_date", "user_id", "transaction_date"),
        Index("ix_transactions_user_category", "user_id", "category"),
        Index("ix_transactions_user_merchant", "user_id", "merchant_clean"),
        Index("ix_transactions_user_nature", "user_id", "transaction_nature"),
        Index("ix_transactions_user_kind", "user_id", "kind"),
    )

    # Split parts go with their parent by ON DELETE CASCADE, so a flush that deletes both may find a part already gone
    __mapper_args__ = {"confirm_deleted_rows": False}

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

    # NULL category = total monthly budget; specific string = per-category (group) limit
    category = Column(String, nullable=True)
    # Set for a budget on one subcategory of `category` (services/taxonomy.py)
    subcategory = Column(String(64), nullable=True)

    # Monthly limit in INR (DECIMAL, always)
    monthly_limit = Column(Numeric(precision=12, scale=2), nullable=False)

    # Soft-delete: deactivate instead of deleting so history is preserved
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="budgets")

    __table_args__ = (
        # One ACTIVE budget per category per user; inactive (deleted) rows don't
        # block re-creating it. COALESCE so the overall cap (NULL) is unique too.
        Index("uq_budgets_user_category_active", "user_id", func.coalesce(text("category"), text("''")),
              func.coalesce(text("subcategory"), text("''")), unique=True, postgresql_where=text("is_active")),
        Index("ix_budgets_user_active", "user_id", "is_active"),
    )

    def __repr__(self) -> str:
        cat = self.category or "TOTAL"
        return f"<Budget {self.id} | {cat} | ₹{self.monthly_limit}/mo>"
