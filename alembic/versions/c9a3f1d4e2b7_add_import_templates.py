"""add import_templates (column mappings keyed by header fingerprint)

Revision ID: c9a3f1d4e2b7
Revises: b7d2e5f81c40
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "c9a3f1d4e2b7"
down_revision = "b7d2e5f81c40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "fingerprint", name="uq_import_template_user_fingerprint"),
    )
    op.create_index("ix_import_templates_user_id", "import_templates", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_import_templates_user_id", table_name="import_templates")
    op.drop_table("import_templates")
