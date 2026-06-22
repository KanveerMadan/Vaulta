"""add transaction_sources table

Revision ID: a1f4c9d27b3e
Revises: c481fe92d6b3
Create Date: 2026-06-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a1f4c9d27b3e"
down_revision = "c481fe92d6b3"
branch_labels = None
depends_on = None

statement_source_type_enum = postgresql.ENUM(
    "bank_csv",
    "bank_pdf",
    "upi_google_pay",
    "upi_phonepe",
    "upi_paytm",
    "manual",
    name="statementsourcetype",
)

transaction_direction_enum = postgresql.ENUM(
    "debit",
    "credit",
    name="transactiondirection",
)


def upgrade() -> None:
    bind = op.get_bind()
    statement_source_type_enum.create(bind, checkfirst=True)
    transaction_direction_enum.create(bind, checkfirst=True)

    op.create_table(
        "transaction_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", statement_source_type_enum, nullable=False),
        sa.Column("direction", transaction_direction_enum, nullable=False),
        sa.Column("utr", sa.String(), nullable=True),
        sa.Column("vpa", sa.String(), nullable=True),
        sa.Column("raw_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_date", sa.Date(), nullable=True),
        sa.Column("raw_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("counterparty_raw", sa.String(), nullable=True),
        sa.Column("raw_row", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("match_tier", sa.SmallInteger(), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_txn_source_user_idempotency"),
    )

    op.create_index("ix_transaction_sources_user_id", "transaction_sources", ["user_id"])
    op.create_index("ix_transaction_sources_transaction_id", "transaction_sources", ["transaction_id"])
    op.create_index("ix_txn_sources_user_utr", "transaction_sources", ["user_id", "utr"])
    op.create_index("ix_txn_sources_user_vpa", "transaction_sources", ["user_id", "vpa"])
    op.create_index("ix_txn_sources_user_transaction", "transaction_sources", ["user_id", "transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_txn_sources_user_transaction", table_name="transaction_sources")
    op.drop_index("ix_txn_sources_user_vpa", table_name="transaction_sources")
    op.drop_index("ix_txn_sources_user_utr", table_name="transaction_sources")
    op.drop_index("ix_transaction_sources_transaction_id", table_name="transaction_sources")
    op.drop_index("ix_transaction_sources_user_id", table_name="transaction_sources")
    op.drop_table("transaction_sources")

    bind = op.get_bind()
    transaction_direction_enum.drop(bind, checkfirst=True)
    statement_source_type_enum.drop(bind, checkfirst=True)