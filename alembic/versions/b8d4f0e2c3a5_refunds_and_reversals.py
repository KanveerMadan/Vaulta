"""refunds and reversals: refund_of_id, auto_category

Revision ID: b8d4f0e2c3a5
Revises: a7c3e9d1b2f4
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "b8d4f0e2c3a5"
down_revision = "a7c3e9d1b2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("auto_category", sa.String(), nullable=True))
    op.execute("UPDATE transactions SET auto_category = category")
    op.add_column("transactions", sa.Column("refund_of_id", sa.UUID(), nullable=True))
    op.create_foreign_key("transactions_refund_of_id_fkey", "transactions", "transactions",
                          ["refund_of_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_transactions_refund_of_id", "transactions", ["refund_of_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_refund_of_id", table_name="transactions")
    op.drop_constraint("transactions_refund_of_id_fkey", "transactions", type_="foreignkey")
    op.drop_column("transactions", "refund_of_id")
    op.drop_column("transactions", "auto_category")
