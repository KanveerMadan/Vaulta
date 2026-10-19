"""baseline: the users table as it existed before Alembic

phase1_initial (45e4169519ab) alters a users table that was created outside
Alembic, so a fresh database couldn't be built. This revision creates that
table, so `alembic upgrade head` works on an empty database.

Existing databases (Neon): their alembic_version is already at or past
45e4169519ab, which now descends from this revision, so Alembic treats it as
applied and never runs it. No stamping needed. See alembic/README.

Revision ID: 0b5e1a9c7d21
Revises:
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = "0b5e1a9c7d21"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("firebase_uid", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("gmail_connected", sa.Boolean(), nullable=True),
        sa.Column("sms_connected", sa.Boolean(), nullable=True),
        sa.Column("aa_connected", sa.Boolean(), nullable=True),
        sa.Column("gmail_access_token", sa.String(), nullable=True),
        sa.Column("gmail_refresh_token", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="users_email_key"),
    )
    op.create_index("ix_users_firebase_uid", "users", ["firebase_uid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_firebase_uid", table_name="users")
    op.drop_table("users")
