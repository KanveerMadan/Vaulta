"""transaction kind and direction; corrections table

kind: spend | income | transfer | refund | reversal | lent | borrowed | repayment
Backfill: self_transfer nature → transfer; credits → income; debits → spend.
direction: taken from the transaction's first source record, else from nature.
Rows already PATCHed in phase 1 (user_corrected = 'true') get a category
correction so detection treats their category as the user's.

Revision ID: f1a2b3c4d5e6
Revises: e5f9c3b7a024
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f1a2b3c4d5e6"
down_revision = "e5f9c3b7a024"
branch_labels = None
depends_on = None

kind_enum = postgresql.ENUM(
    "spend", "income", "transfer", "refund", "reversal", "lent", "borrowed", "repayment",
    name="transactionkind",
)
direction_enum = postgresql.ENUM("debit", "credit", name="transactiondirection", create_type=False)


def upgrade() -> None:
    kind_enum.create(op.get_bind(), checkfirst=True)
    op.add_column("transactions", sa.Column("direction", direction_enum, nullable=True))
    op.add_column("transactions", sa.Column("kind", kind_enum, nullable=True))
    op.execute("""
        UPDATE transactions t SET direction = COALESCE(
            (SELECT s.direction FROM transaction_sources s
              WHERE s.transaction_id = t.id ORDER BY s.created_at LIMIT 1),
            CASE WHEN t.transaction_nature IN ('income', 'peer_payment_received')
                 THEN 'credit'::transactiondirection ELSE 'debit'::transactiondirection END)
    """)
    op.execute("""
        UPDATE transactions SET kind = CASE
            WHEN transaction_nature = 'self_transfer' THEN 'transfer'::transactionkind
            WHEN direction = 'credit' THEN 'income'::transactionkind
            ELSE 'spend'::transactionkind END
    """)
    op.alter_column("transactions", "direction", nullable=False)
    op.alter_column("transactions", "kind", nullable=False)
    op.create_index("ix_transactions_user_kind", "transactions", ["user_id", "kind"])

    op.create_table(
        "corrections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("old_value", sa.String(), nullable=True),
        sa.Column("new_value", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_corrections_transaction_field", "corrections", ["transaction_id", "field"])
    op.create_index("ix_corrections_user", "corrections", ["user_id"])
    op.execute("""
        INSERT INTO corrections (id, user_id, transaction_id, field, old_value, new_value)
        SELECT gen_random_uuid(), user_id, id, 'category', NULL, category
          FROM transactions WHERE user_corrected = 'true'
    """)


def downgrade() -> None:
    op.drop_index("ix_corrections_user", table_name="corrections")
    op.drop_index("ix_corrections_transaction_field", table_name="corrections")
    op.drop_table("corrections")
    op.drop_index("ix_transactions_user_kind", table_name="transactions")
    op.drop_column("transactions", "kind")
    op.drop_column("transactions", "direction")
    kind_enum.drop(op.get_bind(), checkfirst=True)
