"""people.merged_into_id (duplicate people merged automatically or by the user)

Revision ID: c5e1a7b9d0f2
Revises: b4d0f6e8c9a1
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "c5e1a7b9d0f2"
down_revision = "b4d0f6e8c9a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("people", sa.Column("merged_into_id", sa.UUID(), nullable=True))
    op.create_foreign_key("people_merged_into_id_fkey", "people", "people", ["merged_into_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("people_merged_into_id_fkey", "people", type_="foreignkey")
    op.drop_column("people", "merged_into_id")
