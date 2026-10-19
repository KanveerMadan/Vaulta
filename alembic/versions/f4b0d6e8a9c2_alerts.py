"""alerts, users.alert_prefs / quiet hours

Revision ID: f4b0d6e8a9c2
Revises: e3a9c5d7f8b1
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "f4b0d6e8a9c2"
down_revision = "e3a9c5d7f8b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_status", sa.String(length=10), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_alerts_user_key"),
    )
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])
    op.add_column("users", sa.Column("alert_prefs", sa.JSON(), nullable=True))
    op.add_column("users", sa.Column("quiet_start", sa.SmallInteger(), server_default=sa.text("22"), nullable=False))
    op.add_column("users", sa.Column("quiet_end", sa.SmallInteger(), server_default=sa.text("8"), nullable=False))


def downgrade() -> None:
    op.drop_column("users", "quiet_end")
    op.drop_column("users", "quiet_start")
    op.drop_column("users", "alert_prefs")
    op.drop_index("ix_alerts_user_id", table_name="alerts")
    op.drop_table("alerts")
