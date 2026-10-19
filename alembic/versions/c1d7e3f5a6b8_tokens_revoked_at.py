"""users.tokens_revoked_at: sign out everywhere (ID tokens issued before it are refused on every request)

Revision ID: c1d7e3f5a6b8
Revises: b9e5f1a3c4d6
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op

revision = "c1d7e3f5a6b8"
down_revision = "b9e5f1a3c4d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tokens_revoked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "tokens_revoked_at")
