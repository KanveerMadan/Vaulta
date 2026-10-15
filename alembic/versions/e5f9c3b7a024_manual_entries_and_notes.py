"""manual transaction source and transaction notes

Revision ID: e5f9c3b7a024
Revises: d4e8b2a6f913
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "e5f9c3b7a024"
down_revision = "d4e8b2a6f913"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE transactionsource ADD VALUE IF NOT EXISTS 'manual'")
    op.add_column("transactions", sa.Column("notes", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "notes")
    # 'manual' stays in the enum: Postgres can't drop enum values.
