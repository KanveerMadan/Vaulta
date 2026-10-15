"""cash wallet: transactions.cash_flow, cash_declarations, users.cash_reminded_week

Revision ID: d2f8b4c6e7a9
Revises: c1e7a3b5d6f8
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "d2f8b4c6e7a9"
down_revision = "c1e7a3b5d6f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("cash_flow", sa.String(length=10), nullable=True))
    op.add_column("users", sa.Column("cash_reminded_week", sa.Date(), nullable=True))
    op.create_table(
        "cash_declarations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(length=12), nullable=False),
        sa.Column("declared_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cash_declarations_user_id", "cash_declarations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_cash_declarations_user_id", table_name="cash_declarations")
    op.drop_table("cash_declarations")
    op.drop_column("users", "cash_reminded_week")
    op.drop_column("transactions", "cash_flow")
