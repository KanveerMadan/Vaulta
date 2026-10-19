"""Imports: one row per statement upload, so it can be deleted on its own (Settings → Imports).

transaction_sources.import_id links each source row to its upload; rows imported before this have none and are
deleted by source instead.

Revision ID: c8d4e6f0a1b3
Revises: b7c3d5e9f0a2
Create Date: 2026-10-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "c8d4e6f0a1b3"
down_revision = "b7c3d5e9f0a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "imports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_label", sa.String(60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.execute("ALTER TABLE imports ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY user_isolation ON imports USING (user_id = vaulta_current_user_id()) "
               "WITH CHECK (user_id = vaulta_current_user_id())")
    op.add_column("transaction_sources", sa.Column("import_id", UUID(as_uuid=True),
                  sa.ForeignKey("imports.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_txn_sources_user_import", "transaction_sources", ["user_id", "import_id"])
    op.execute("""
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaulta_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON imports TO vaulta_app;
  END IF;
END $$;""")


def downgrade() -> None:
    op.drop_index("ix_txn_sources_user_import", table_name="transaction_sources")
    op.drop_column("transaction_sources", "import_id")
    op.drop_table("imports")
