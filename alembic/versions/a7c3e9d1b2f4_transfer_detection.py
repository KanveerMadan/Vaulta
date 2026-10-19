"""own-account transfer detection: transfer_group_id, source_label

Revision ID: a7c3e9d1b2f4
Revises: f1a2b3c4d5e6
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "a7c3e9d1b2f4"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("transfer_group_id", sa.UUID(), nullable=True))
    op.create_index("ix_transactions_transfer_group_id", "transactions", ["transfer_group_id"])
    op.add_column("transaction_sources", sa.Column("source_label", sa.String(length=60), nullable=True))
    # Imported rows kept the sanitized row (incl. source_label) in raw_row
    op.execute("UPDATE transaction_sources SET source_label = raw_row->>'source_label' WHERE raw_row IS NOT NULL")


def downgrade() -> None:
    op.drop_column("transaction_sources", "source_label")
    op.drop_index("ix_transactions_transfer_group_id", table_name="transactions")
    op.drop_column("transactions", "transfer_group_id")
