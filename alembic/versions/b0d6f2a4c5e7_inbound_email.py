"""inbound bank-alert email: forwarding tokens, events, Gmail confirmations; email_alert source

Revision ID: b0d6f2a4c5e7
Revises: a9c5e1f3b4d6
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "b0d6f2a4c5e7"
down_revision = "a9c5e1f3b4d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE statementsourcetype ADD VALUE IF NOT EXISTS 'email_alert'")
    op.add_column("users", sa.Column("inbound_token_hash", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("inbound_token_encrypted", sa.String(), nullable=True))
    op.create_unique_constraint("users_inbound_token_hash_key", "users", ["inbound_token_hash"])
    op.create_table(
        "inbound_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("bank_key", sa.String(length=20), nullable=True),
        sa.Column("bank_name", sa.String(length=60), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbound_events_user_received", "inbound_events", ["user_id", "received_at"])
    op.create_table(
        "gmail_confirmations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column("code", sa.String(length=20), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gmail_confirmations_user_id", "gmail_confirmations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_gmail_confirmations_user_id", table_name="gmail_confirmations")
    op.drop_table("gmail_confirmations")
    op.drop_index("ix_inbound_events_user_received", table_name="inbound_events")
    op.drop_table("inbound_events")
    op.drop_constraint("users_inbound_token_hash_key", "users", type_="unique")
    op.drop_column("users", "inbound_token_encrypted")
    op.drop_column("users", "inbound_token_hash")
