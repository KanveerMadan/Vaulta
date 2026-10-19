"""pending_auth_deletions: a deleted account whose Firebase login is still to be deleted (and confirmed by email)

Written in the same transaction that deletes the account's rows, so a failure afterwards always leaves a record
the hourly run completes (services/deletion.py). Holds the Firebase uid and the address for the confirmation email
only until the deletion completes. Not user data afterwards, so no row-level security; the API role may use it.

Revision ID: e3f9a5b7c8d0
Revises: d2e8f4a6b7c9
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "e3f9a5b7c8d0"
down_revision = "d2e8f4a6b7c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_auth_deletions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("firebase_uid", sa.String(), nullable=False, unique=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(80), nullable=True),
    )
    op.execute("""
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaulta_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON pending_auth_deletions TO vaulta_app;
  END IF;
END $$;""")


def downgrade() -> None:
    op.drop_table("pending_auth_deletions")
