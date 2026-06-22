"""add transaction_nature field

Revision ID: c481fe92d6b3
Revises: 9e4e79816de3
Create Date: 2026-06-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c481fe92d6b3"
down_revision = "9e4e79816de3"
branch_labels = None
depends_on = None

transaction_nature_enum = postgresql.ENUM(
    "expense",
    "income",
    "peer_payment_sent",
    "peer_payment_received",
    "self_transfer",
    name="transactionnature",
)


def upgrade() -> None:
    bind = op.get_bind()
    transaction_nature_enum.create(bind, checkfirst=True)

    op.add_column(
        "transactions",
        sa.Column(
            "transaction_nature",
            transaction_nature_enum,
            nullable=False,
            server_default="expense",
        ),
    )

    op.create_index(
        "ix_transactions_user_nature",
        "transactions",
        ["user_id", "transaction_nature"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_user_nature", table_name="transactions")
    op.drop_column("transactions", "transaction_nature")

    bind = op.get_bind()
    transaction_nature_enum.drop(bind, checkfirst=True)