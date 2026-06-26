"""Alembic environment — wired to the vja schema + the VJA_DATABASE_URL.

The DB URL is resolved the same way the app resolves it (`vja.db.engine.DEFAULT_DATABASE_URL`), so
migrations and runtime always target the same database. SQLite uses batch ("move and copy") mode so
future ALTERs work despite SQLite's limited ALTER TABLE.

Migrations run with SQLite **foreign keys OFF** (the app's runtime engine keeps them ON). A batch
table-rebuild — e.g. adding the `profiles.user_id` FK — drops and recreates the table; with FK
enforcement on, that trips any *referencing* table (`matches → profiles`) the moment the DB holds
real rows. Disabling FKs for the rebuild is exactly SQLite's documented ALTER procedure, and the
pragma is a no-op inside a transaction, so it's set at connect time (not via the runtime listener).
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, event

from vja.db.engine import DEFAULT_DATABASE_URL
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


def _migration_engine():  # type: ignore[no-untyped-def]
    """The engine migrations run on. Unlike the app's `get_engine`, it sets SQLite foreign keys OFF
    (at connect, before alembic's transaction) so batch table-rebuilds don't trip referencing tables."""
    engine = create_engine(_DB_URL)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fks_off(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.close()

    return engine


def run_migrations_online() -> None:
    connectable = _migration_engine()
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
