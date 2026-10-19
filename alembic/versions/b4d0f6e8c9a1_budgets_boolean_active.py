"""budgets: is_active boolean, unique only among active rows

Deleting a budget soft-deletes it (is_active = false), but the old
unique (user_id, category) constraint still covered deleted rows, so
re-creating a deleted category's budget failed. Now uniqueness is a partial
index over active rows, with COALESCE so the overall cap (NULL category)
is unique too.

Revision ID: b4d0f6e8c9a1
Revises: a3c9e5d7b8f0
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "b4d0f6e8c9a1"
down_revision = "a3c9e5d7b8f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_budget_user_category", "budgets", type_="unique")
    op.drop_index("ix_budgets_user_active", table_name="budgets")
    op.alter_column("budgets", "is_active", type_=sa.Boolean(), postgresql_using="is_active = 'true'",
                    server_default=sa.text("true"), existing_nullable=False)
    op.create_index("ix_budgets_user_active", "budgets", ["user_id", "is_active"])
    op.execute(
        "CREATE UNIQUE INDEX uq_budgets_user_category_active ON budgets (user_id, COALESCE(category, '')) WHERE is_active"
    )


def downgrade() -> None:
    op.drop_index("uq_budgets_user_category_active", table_name="budgets")
    op.drop_index("ix_budgets_user_active", table_name="budgets")
    op.alter_column("budgets", "is_active", type_=sa.String(), server_default=None,
                    postgresql_using="CASE WHEN is_active THEN 'true' ELSE 'false' END", existing_nullable=False)
    op.create_index("ix_budgets_user_active", "budgets", ["user_id", "is_active"])
    # Only one row per (user, category) may remain for the old constraint
    op.execute("""
        DELETE FROM budgets b USING budgets newer
        WHERE b.user_id = newer.user_id AND b.category IS NOT DISTINCT FROM newer.category
          AND b.is_active = 'false' AND b.id <> newer.id
    """)
    op.create_unique_constraint("uq_budget_user_category", "budgets", ["user_id", "category"])
