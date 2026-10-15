"""drop unused gmail token columns from users

Gmail integration was removed (see Connect.jsx); nothing reads or writes these.

Revision ID: b7d2e5f81c40
Revises: a1f4c9d27b3e
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "b7d2e5f81c40"
down_revision = "a1f4c9d27b3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "gmail_access_token")
    op.drop_column("users", "gmail_refresh_token")
    op.drop_column("users", "gmail_last_sync_at")


def downgrade() -> None:
    op.add_column("users", sa.Column("gmail_last_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("gmail_refresh_token", sa.String(), nullable=True))
    op.add_column("users", sa.Column("gmail_access_token", sa.String(), nullable=True))
