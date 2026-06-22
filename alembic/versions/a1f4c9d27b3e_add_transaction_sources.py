"""add transaction_sources table

Revision ID: a1f4c9d27b3e
Revises: c481fe92d6b3
Create Date: 2026-06-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "a1f4c9d27b3e"
down_revision = "c481fe92d6b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE statementsourcetype AS ENUM (
                'bank_csv', 'bank_pdf', 'upi_google_pay',
                'upi_phonepe', 'upi_paytm', 'manual'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE transactiondirection AS ENUM ('debit', 'credit');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS transaction_sources (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            transaction_id UUID REFERENCES transactions(id) ON DELETE SET NULL,
            source statementsourcetype NOT NULL,
            direction transactiondirection NOT NULL,
            utr VARCHAR,
            vpa VARCHAR,
            raw_timestamp TIMESTAMPTZ,
            raw_date DATE,
            raw_amount NUMERIC(12, 2) NOT NULL,
            counterparty_raw VARCHAR,
            raw_row JSON,
            idempotency_key VARCHAR(64) NOT NULL,
            match_tier SMALLINT,
            matched_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_txn_source_user_idempotency UNIQUE (user_id, idempotency_key)
        );
    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_transaction_sources_user_id ON transaction_sources (user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_transaction_sources_transaction_id ON transaction_sources (transaction_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_txn_sources_user_utr ON transaction_sources (user_id, utr);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_txn_sources_user_vpa ON transaction_sources (user_id, vpa);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_txn_sources_user_transaction ON transaction_sources (user_id, transaction_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_txn_sources_user_transaction;")
    op.execute("DROP INDEX IF EXISTS ix_txn_sources_user_vpa;")
    op.execute("DROP INDEX IF EXISTS ix_txn_sources_user_utr;")
    op.execute("DROP INDEX IF EXISTS ix_transaction_sources_transaction_id;")
    op.execute("DROP INDEX IF EXISTS ix_transaction_sources_user_id;")
    op.execute("DROP TABLE IF EXISTS transaction_sources;")
    op.execute("DROP TYPE IF EXISTS transactiondirection;")
    op.execute("DROP TYPE IF EXISTS statementsourcetype;")