"""people and transactions.person_id

Revision ID: d0f6b2a4e5c7
Revises: c9e5a1f3d4b6
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "d0f6b2a4e5c7"
down_revision = "c9e5a1f3d4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "people",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("masked_vpa", sa.String(length=80), nullable=True),
        sa.Column("tag", sa.String(length=20), nullable=True),
        sa.Column("default_category", sa.String(), nullable=True),
        sa.Column("default_kind", sa.String(length=12), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key_hash", name="uq_people_user_key"),
    )
    op.create_index("ix_people_user_id", "people", ["user_id"])
    op.add_column("transactions", sa.Column("person_id", sa.UUID(), nullable=True))
    op.create_foreign_key("transactions_person_id_fkey", "transactions", "people", ["person_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_transactions_person_id", "transactions", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_person_id", table_name="transactions")
    op.drop_constraint("transactions_person_id_fkey", "transactions", type_="foreignkey")
    op.drop_column("transactions", "person_id")
    op.drop_index("ix_people_user_id", table_name="people")
    op.drop_table("people")
