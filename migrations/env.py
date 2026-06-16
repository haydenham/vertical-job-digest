"""Alembic environment — wired to the vja schema + the VJA_DATABASE_URL.

The DB URL is resolved the same way the app resolves it (vja.db.engine), so migrations
and runtime always target the same database. SQLite uses batch ("move and copy") mode
so future ALTERs work despite SQLite's limited ALTER TABLE.
"""

import os
from logging.config import fileConfig

from alembic import context

from vja.db.engine import DEFAULT_DATABASE_URL, get_engine
from vja.db.schema import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata

_DB_URL = os.environ.get("VJA_DATABASE_URL", DEFAULT_DATABASE_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=_DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_DB_URL.startswith("sqlite"),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = get_engine(_DB_URL)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
