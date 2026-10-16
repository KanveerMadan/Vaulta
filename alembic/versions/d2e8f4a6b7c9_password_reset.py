"""password reset requests: users.password_reset_requested_at, and vaulta_find_user can look up by email

Revision ID: d2e8f4a6b7c9
Revises: c1d7e3f5a6b8
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op

revision = "d2e8f4a6b7c9"
down_revision = "c1d7e3f5a6b8"
branch_labels = None
depends_on = None

FIND_USER = """
CREATE OR REPLACE FUNCTION vaulta_find_user(field text, value text) RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE found uuid;
BEGIN
  IF field = 'firebase_uid' THEN SELECT id INTO found FROM users WHERE firebase_uid = value;
  ELSIF field = 'inbound_token_hash' THEN SELECT id INTO found FROM users WHERE inbound_token_hash = value;
  ELSIF field = 'telegram_chat_id' THEN SELECT id INTO found FROM users WHERE telegram_chat_id = value::bigint;
  ELSIF field = 'razorpay_subscription_id' THEN SELECT id INTO found FROM users WHERE razorpay_subscription_id = value LIMIT 1;
  EMAIL_BRANCH
  ELSE RAISE EXCEPTION 'vaulta_find_user: unknown field %', field;
  END IF;
  RETURN found;
END $$;
"""
EMAIL = "ELSIF field = 'email' THEN SELECT id INTO found FROM users WHERE lower(email) = lower(value) LIMIT 1;"


def upgrade() -> None:
    op.add_column("users", sa.Column("password_reset_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(FIND_USER.replace("EMAIL_BRANCH", EMAIL))


def downgrade() -> None:
    op.execute(FIND_USER.replace("EMAIL_BRANCH", ""))
    op.drop_column("users", "password_reset_requested_at")
