"""Merchant model: transactions.category_explanation, recategorisation_runs (row-level security), model_metrics
(aggregate counts, no user or merchant), users.ml_training_consent.

Revision ID: a6b2c4d8e0f1
Revises: f5a1b3c7d9e2
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "a6b2c4d8e0f1"
down_revision = "f5a1b3c7d9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("category_explanation", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("ml_training_consent", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_table(
        "recategorisation_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed", sa.Integer(), nullable=False),
        sa.Column("changes", sa.Text(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
    )
    op.execute("ALTER TABLE recategorisation_runs ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY user_isolation ON recategorisation_runs USING (user_id = vaulta_current_user_id()) "
               "WITH CHECK (user_id = vaulta_current_user_id())")
    op.create_table(
        "model_metrics",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("source", sa.String(20), primary_key=True),
        sa.Column("categorised", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("corrected", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("""
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaulta_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON recategorisation_runs, model_metrics TO vaulta_app;
  END IF;
END $$;""")


def downgrade() -> None:
    op.drop_table("model_metrics")
    op.drop_table("recategorisation_runs")
    op.drop_column("users", "ml_training_consent")
    op.drop_column("transactions", "category_explanation")
