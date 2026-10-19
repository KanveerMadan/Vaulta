"""reports; recurring_series.established_on

Revision ID: f8b4d0e2a3c5
Revises: e7a3c9d1f2b4
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "f8b4d0e2a3c5"
down_revision = "e7a3c9d1f2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recurring_series", sa.Column("established_on", sa.Date(), nullable=True))
    op.create_table(
        "reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("period_type", sa.String(length=10), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("json", sa.JSON(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("narrative_source", sa.String(length=10), nullable=False),
        sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "period_type", "period_start", name="uq_reports_user_period"),
    )
    op.create_index("ix_reports_user_id", "reports", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_user_id", table_name="reports")
    op.drop_table("reports")
    op.drop_column("recurring_series", "established_on")
