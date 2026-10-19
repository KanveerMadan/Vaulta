"""chat history, proposed actions, users.ai_chat_enabled

Revision ID: d6f2b8c0e1a3
Revises: c5e1a7b9d0f2
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "d6f2b8c0e1a3"
down_revision = "c5e1a7b9d0f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ai_chat_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_user_session", "chat_messages", ["user_id", "session_id", "created_at"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])
    op.create_table(
        "chat_actions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("tool", sa.String(length=40), nullable=False),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_chat_actions_user_id", "chat_actions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_actions_user_id", table_name="chat_actions")
    op.drop_table("chat_actions")
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_user_session", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_column("users", "ai_chat_enabled")
