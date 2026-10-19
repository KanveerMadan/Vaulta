"""anomalies

Revision ID: e7a3c9d1f2b4
Revises: d6f2b8c0e1a3
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "e7a3c9d1f2b4"
down_revision = "d6f2b8c0e1a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anomalies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_anomalies_user_key"),
    )
    op.create_index("ix_anomalies_user_id", "anomalies", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_anomalies_user_id", table_name="anomalies")
    op.drop_table("anomalies")
