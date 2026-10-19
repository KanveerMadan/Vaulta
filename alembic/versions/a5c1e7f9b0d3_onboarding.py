"""users.onboarding

Revision ID: a5c1e7f9b0d3
Revises: f4b0d6e8a9c2
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "a5c1e7f9b0d3"
down_revision = "f4b0d6e8a9c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("onboarding", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "onboarding")
