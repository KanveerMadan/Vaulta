"""users: timezone, which reports are built and emailed

Revision ID: a9c5e1f3b4d6
Revises: f8b4d0e2a3c5
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "a9c5e1f3b4d6"
down_revision = "f8b4d0e2a3c5"
branch_labels = None
depends_on = None

FLAGS = ("reports_weekly", "reports_monthly", "reports_annual", "email_weekly", "email_monthly", "email_annual")


def upgrade() -> None:
    op.add_column("users", sa.Column("timezone", sa.String(length=64), server_default="Asia/Kolkata", nullable=False))
    for flag in FLAGS:
        op.add_column("users", sa.Column(flag, sa.Boolean(), server_default=sa.text("true"), nullable=False))


def downgrade() -> None:
    for flag in reversed(FLAGS):
        op.drop_column("users", flag)
    op.drop_column("users", "timezone")
