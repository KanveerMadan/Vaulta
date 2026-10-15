"""split transactions: is_split, split_parent_id

Revision ID: f2b8d4c6a7e9
Revises: e1a7c3b5f6d8
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "f2b8d4c6a7e9"
down_revision = "e1a7c3b5f6d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("is_split", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("transactions", sa.Column("split_parent_id", sa.UUID(), nullable=True))
    op.create_foreign_key("transactions_split_parent_id_fkey", "transactions", "transactions",
                          ["split_parent_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_transactions_split_parent_id", "transactions", ["split_parent_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_split_parent_id", table_name="transactions")
    op.drop_constraint("transactions_split_parent_id_fkey", "transactions", type_="foreignkey")
    op.drop_column("transactions", "split_parent_id")
    op.drop_column("transactions", "is_split")
