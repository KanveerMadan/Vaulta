"""recurring_series

Revision ID: c9e5a1f3d4b6
Revises: b8d4f0e2c3a5
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "c9e5a1f3d4b6"
down_revision = "b8d4f0e2c3a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_series",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("cadence", sa.String(length=10), nullable=False),
        sa.Column("typical_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("last_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("last_date", sa.Date(), nullable=False),
        sa.Column("next_expected", sa.Date(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("type_guess", sa.String(length=15), nullable=False),
        sa.Column("previous_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("user_status", sa.String(length=10), nullable=True),
        sa.Column("user_name", sa.String(length=100), nullable=True),
        sa.Column("user_type", sa.String(length=15), nullable=True),
        sa.Column("usage", sa.String(length=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_recurring_user_key"),
    )
    op.create_index("ix_recurring_series_user_id", "recurring_series", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_recurring_series_user_id", table_name="recurring_series")
    op.drop_table("recurring_series")
