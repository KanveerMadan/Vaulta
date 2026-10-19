"""add credit_card to statementsourcetype

Revision ID: d4e8b2a6f913
Revises: c9a3f1d4e2b7
Create Date: 2026-10-15
"""
from alembic import op


revision = "d4e8b2a6f913"
down_revision = "c9a3f1d4e2b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE statementsourcetype ADD VALUE IF NOT EXISTS 'credit_card'")


def downgrade() -> None:
    # Postgres can't drop an enum value; rows using it would have to be
    # rewritten first. Leaving the value in place is harmless.
    pass
