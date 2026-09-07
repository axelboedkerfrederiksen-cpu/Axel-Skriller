from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from price_monitor.db.base import Base
from price_monitor.db.models import ALL_MODELS  # noqa: F401
from price_monitor.db.session import create_db_engine, normalize_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def configured_database_url() -> str:
    return os.getenv(
        "PRICE_MONITOR_MIGRATION_DATABASE_URL",
        os.getenv(
            "PRICE_MONITOR_DATABASE_URL",
            config.get_main_option("sqlalchemy.url"),
        ),
    )


def run_migrations_offline() -> None:
    context.configure(
        url=str(normalize_database_url(configured_database_url())),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_db_engine(configured_database_url())
    try:
        with connectable.connect() as connection:
            run_migrations(connection)
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
