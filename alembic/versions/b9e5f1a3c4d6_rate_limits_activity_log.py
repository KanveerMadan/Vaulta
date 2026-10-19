"""rate_limits (shared counters), activity_log (row-level security), users.last_sign_in_at

Revision ID: b9e5f1a3c4d6
Revises: a7c3e9f1d2b4
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "b9e5f1a3c4d6"
down_revision = "a7c3e9f1d2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limits",
        sa.Column("bucket", sa.String(64), primary_key=True),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rate_limits_reset_at", "rate_limits", ["reset_at"])
    op.create_table(
        "activity_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_activity_log_user_created", "activity_log", ["user_id", "created_at"])
    op.execute("ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY user_isolation ON activity_log USING (user_id = vaulta_current_user_id()) "
               "WITH CHECK (user_id = vaulta_current_user_id())")
    op.add_column("users", sa.Column("last_sign_in_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("""
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaulta_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limits, activity_log TO vaulta_app;
  END IF;
END $$;""")


def downgrade() -> None:
    op.drop_column("users", "last_sign_in_at")
    op.drop_table("activity_log")
    op.drop_table("rate_limits")
