"""Two-level taxonomy and tags: transactions.subcategory/auto_subcategory, budgets.subcategory, custom_subcategories,
tags, transaction_tags (row-level security on the three new tables).

Existing categories are already the taxonomy's group names, so no transaction or budget changes value here.
Subcategories for existing rows (and Policybazaar's move from Finance to Insurance in the normalizer) are applied by the
re-categorisation job, which can be dry-run and undone and never touches what the user corrected
(services/recategorise.py), not by this migration: merchant names are encrypted, so SQL can't see them.

Revision ID: f5a1b3c7d9e2
Revises: e3f9a5b7c8d0
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "f5a1b3c7d9e2"
down_revision = "e3f9a5b7c8d0"
branch_labels = None
depends_on = None

NEW_TABLES = ("custom_subcategories", "tags", "transaction_tags")


def upgrade() -> None:
    op.add_column("transactions", sa.Column("subcategory", sa.String(64), nullable=True))
    op.add_column("transactions", sa.Column("auto_subcategory", sa.String(64), nullable=True))
    op.add_column("budgets", sa.Column("subcategory", sa.String(64), nullable=True))
    op.drop_index("uq_budgets_user_category_active", table_name="budgets")
    op.execute("CREATE UNIQUE INDEX uq_budgets_user_category_active ON budgets "
               "(user_id, COALESCE(category, ''), COALESCE(subcategory, '')) WHERE is_active")

    op.create_table(
        "custom_subcategories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("group", sa.String(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "group", "name", name="uq_custom_subcategories_user_group_name"),
    )
    op.create_table(
        "tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
    )
    op.create_table(
        "transaction_tags",
        sa.Column("transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", UUID(as_uuid=True), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    )
    op.execute("ALTER TABLE custom_subcategories ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY user_isolation ON custom_subcategories USING (user_id = vaulta_current_user_id()) "
               "WITH CHECK (user_id = vaulta_current_user_id())")
    op.execute("ALTER TABLE tags ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY user_isolation ON tags USING (user_id = vaulta_current_user_id()) "
               "WITH CHECK (user_id = vaulta_current_user_id())")
    op.execute("ALTER TABLE transaction_tags ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY user_isolation ON transaction_tags USING (user_id = vaulta_current_user_id()) "
               "WITH CHECK (user_id = vaulta_current_user_id())")
    op.execute("""
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaulta_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON custom_subcategories, tags, transaction_tags TO vaulta_app;
  END IF;
END $$;""")


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
    op.drop_index("uq_budgets_user_category_active", table_name="budgets")
    op.execute("DELETE FROM budgets WHERE subcategory IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_budgets_user_category_active ON budgets (user_id, COALESCE(category, '')) WHERE is_active")
    op.drop_column("budgets", "subcategory")
    op.drop_column("transactions", "auto_subcategory")
    op.drop_column("transactions", "subcategory")
