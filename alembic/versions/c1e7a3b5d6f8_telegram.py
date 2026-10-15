"""telegram: linked chat, weekly summary flag, link codes, pending entries

Revision ID: c1e7a3b5d6f8
Revises: b0d6f2a4c5e7
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "c1e7a3b5d6f8"
down_revision = "b0d6f2a4c5e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
    op.create_unique_constraint("users_telegram_chat_id_key", "users", ["telegram_chat_id"])
    op.add_column("users", sa.Column("telegram_weekly", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("reports", sa.Column("telegram_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "telegram_link_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index("ix_telegram_link_codes_user_id", "telegram_link_codes", ["user_id"])
    op.create_table(
        "telegram_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telegram_entries_user_saved", "telegram_entries", ["user_id", "saved_at"])


def downgrade() -> None:
    op.drop_index("ix_telegram_entries_user_saved", table_name="telegram_entries")
    op.drop_table("telegram_entries")
    op.drop_index("ix_telegram_link_codes_user_id", table_name="telegram_link_codes")
    op.drop_table("telegram_link_codes")
    op.drop_column("reports", "telegram_sent_at")
    op.drop_column("users", "telegram_weekly")
    op.drop_constraint("users_telegram_chat_id_key", "users", type_="unique")
    op.drop_column("users", "telegram_chat_id")
