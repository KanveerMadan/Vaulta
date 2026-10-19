"""review_dismissals

Revision ID: a3c9e5d7b8f0
Revises: f2b8d4c6a7e9
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "a3c9e5d7b8f0"
down_revision = "f2b8d4c6a7e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_dismissals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("card_id", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "card_id", name="uq_review_dismissals_user_card"),
    )
    op.create_index("ix_review_dismissals_user_id", "review_dismissals", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_review_dismissals_user_id", table_name="review_dismissals")
    op.drop_table("review_dismissals")
