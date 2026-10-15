"""goals and goal entries

Revision ID: e3a9c5d7f8b1
Revises: d2f8b4c6e7a9
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "e3a9c5d7f8b1"
down_revision = "d2f8b4c6e7a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("target_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goals_user_id", "goals", ["user_id"])
    op.create_table(
        "goal_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("goal_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goal_entries_goal_id", "goal_entries", ["goal_id"])
    op.create_index("ix_goal_entries_user_id", "goal_entries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_goal_entries_user_id", table_name="goal_entries")
    op.drop_index("ix_goal_entries_goal_id", table_name="goal_entries")
    op.drop_table("goal_entries")
    op.drop_index("ix_goals_user_id", table_name="goals")
    op.drop_table("goals")
