"""
Alembic migration environment.

Run migrations:
  alembic upgrade head

Generate a new migration (after model changes):
  alembic revision --autogenerate -m "description"

IMPORTANT: All model modules must be imported here so Alembic's autogenerate
can see the full metadata. Add new model imports here as models are created.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# alembic/ and backend/ are siblings under vaulta/ — add backend/ to path so
# `app.*` imports resolve (that's where app/ actually lives).
_VAULTA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND_DIR = os.path.join(_VAULTA_ROOT, "backend")
sys.path.insert(0, _BACKEND_DIR)

# ── Model imports — ALL models must be registered here ────────────────────────
from app.core.database import Base  # noqa: F401
from app.models.user import User, Household  # noqa: F401
from app.models.transaction import Transaction, Budget  # noqa: F401
# Phase 2+: import new models here as they're created

# ── Config ────────────────────────────────────────────────────────────────────
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """
    Read DATABASE_URL from environment — never from alembic.ini (no secrets in source).
    Neon requires ?sslmode=require; add it if not already present.
    """
    from app.core.config import settings
    url = settings.DATABASE_URL
    if "sslmode" not in url and "neon.tech" in url:
        url += "?sslmode=require"
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection needed)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Detect column type changes
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live DB connection (standard mode)."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No pooling during migrations
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()