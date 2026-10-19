"""Preview layer: transactions.is_sample/simulation_id, transaction_sources.is_sample (core/samples.py).

Revision ID: b7c3d5e9f0a2
Revises: a6b2c4d8e0f1
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "b7c3d5e9f0a2"
down_revision = "a6b2c4d8e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("transactions", sa.Column("simulation_id", UUID(as_uuid=True), nullable=True))
    op.add_column("transaction_sources", sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    # the hourly clean-up finds a user's samples quickly; real rows (almost all) stay out of this index
    op.create_index("ix_transactions_samples", "transactions", ["user_id", "created_at"], postgresql_where=sa.text("is_sample"))


def downgrade() -> None:
    op.drop_index("ix_transactions_samples", table_name="transactions")
    op.drop_column("transaction_sources", "is_sample")
    op.drop_column("transactions", "simulation_id")
    op.drop_column("transactions", "is_sample")
