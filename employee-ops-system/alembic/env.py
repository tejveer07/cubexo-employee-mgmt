"""
alembic/env.py — Alembic migration environment.

Inherits the DB URL from app.database so we always point at the same SQLite file
regardless of whether we're running in dev or packaged mode.
"""

import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Make sure the project root is on sys.path when running `alembic` from the
# employee-ops-system/ directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import DATABASE_URL, Base
import app.models  # noqa: F401 — registers all models with Base.metadata

# Alembic Config object
config = context.config

# Override sqlalchemy.url with the resolved path from database.py
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Logging setup from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
