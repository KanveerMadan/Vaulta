"""
Transaction source records — the raw, per-source evidence behind every
canonical Transaction. See VAULTA master prompt, Section 4.

A row here is created for every parsed transaction line, from every source
(bank CSV/PDF, UPI app PDF, manual entry), BEFORE/AS it's matched against (or
becomes) a canonical Transaction. This is what makes cross-source dedup
possible and reversible: the original evidence is never overwritten or
discarded, only linked.
"""

import re
import uuid
import enum
from datetime import date as date_type

from sqlalchemy import (
    Column, String, Numeric, DateTime, Date, ForeignKey,
    Enum as SAEnum, Index, UniqueConstraint, JSON, SmallInteger, text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class StatementSourceType(str, enum.Enum):
    """
    Which specific statement/channel a transaction_sources row came from.

    Deliberately a SEPARATE enum from the existing `TransactionSource` on
    Transaction.source (gmail/sms/csv/aa). That enum predates the Phase 1.5
    data-strategy pivot and is now stale — no `upi` value, and `gmail`/`aa`
    are still listed as if live, despite both being permanently removed
    (Section 3). Reconciling the two enums — likely by retiring
    Transaction.source in favor of this one, or deriving one from the other —
    is an open decision for a future session. Not resolved here since it
    touches an existing column and existing production data.
    """
    bank_csv = "bank_csv"
    bank_pdf = "bank_pdf"
    upi_google_pay = "upi_google_pay"
    upi_phonepe = "upi_phonepe"
    upi_paytm = "upi_paytm"
    manual = "manual"


class TransactionDirection(str, enum.Enum):
    """
    Money-in vs money-out for THIS raw source row, as stated by the source
    itself (a CSV debit/credit column, or a UPI statement's "Paid to" /
    "Received from" / "Self transfer to" label).

    Not part of the original Section 4 schema sketch — added because Section
    4's matching hierarchy requires a hard direction filter ("a debit can
    never match a credit") and nothing else in the schema carries that signal
    explicitly. The canonical Transaction model still has no direction field
    of its own; dedup_matcher.py infers a Transaction's direction from its
    transaction_nature when needed (see _infer_transaction_direction there).
    """
    debit = "debit"
    credit = "credit"


class TransactionSourceRecord(Base):
    __tablename__ = "transaction_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Nullable until matched/linked. SET NULL (not CASCADE) on the Transaction
    # FK so this row's raw evidence survives even if the Transaction it was
    # merged into is later deleted/rebuilt — preserving it for re-derivation,
    # per Section 4's "never silently destructive" requirement.
    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    source = Column(SAEnum(StatementSourceType), nullable=False)
    direction = Column(SAEnum(TransactionDirection), nullable=False)

    # Matching signals, strongest to weakest — see Section 4 tier hierarchy.
    # All nullable: not every source provides every signal (a bank CSV
    # typically has no UTR, no VPA, and date-only precision).
    utr = Column(String, nullable=True)
    vpa = Column(String, nullable=True)
    raw_timestamp = Column(DateTime(timezone=True), nullable=True)
    raw_date = Column(Date, nullable=True)
    raw_amount = Column(Numeric(precision=12, scale=2), nullable=False)

    # Counterparty/merchant text as it appeared in THIS specific source, used
    # for tier 3/4 merchant-overlap comparison. Distinct from the canonical
    # Transaction's merchant_clean/merchant_raw, which may be enriched later
    # by a higher-quality source.
    counterparty_raw = Column(String, nullable=True)

    # Full original row, preserved for re-derivation/audit if a match is
    # later found to be wrong.
    raw_row = Column(JSON, nullable=True)

    # Same convention as Transaction.idempotency_key — re-ingesting the same
    # statement twice must be safe at the source-record level too, regardless
    # of whether the row ends up matched to an existing Transaction.
    idempotency_key = Column(String(64), nullable=False)

    # Which tier of Section 4's hierarchy produced the match (1-4), or NULL if
    # this row had no match and became a new canonical Transaction instead.
    # Kept for debugging/tuning — Section 4 explicitly flags tier 4 as needing
    # tuning against real multi-source data once available.
    match_tier = Column(SmallInteger, nullable=True)
    matched_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    transaction = relationship("Transaction", back_populates="source_records")

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_txn_source_user_idempotency"),
        Index("ix_txn_sources_user_utr", "user_id", "utr"),
        Index("ix_txn_sources_user_vpa", "user_id", "vpa"),
        Index("ix_txn_sources_user_transaction", "user_id", "transaction_id"),
    )

    def __repr__(self) -> str:
        tier = self.match_tier if self.match_tier is not None else "unmatched"
        return f"<TransactionSourceRecord {self.id} | {self.source.value} | ₹{self.raw_amount} | tier={tier}>"