"""rules (merchant → category/kind)

Revision ID: e1a7c3b5f6d8
Revises: d0f6b2a4e5c7
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "e1a7c3b5f6d8"
down_revision = "d0f6b2a4e5c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("merchant_key", sa.String(length=100), nullable=False),
        sa.Column("merchant_label", sa.String(length=100), nullable=False),
        sa.Column("field", sa.String(length=16), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("origin", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "merchant_key", "field", name="uq_rules_user_merchant_field"),
    )
    op.create_index("ix_rules_user_id", "rules", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_rules_user_id", table_name="rules")
    op.drop_table("rules")
