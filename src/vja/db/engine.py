"""Database engine + connection helpers.

The DB URL comes from `VJA_DATABASE_URL` (default local SQLite); it is the single
thing that changes for the Postgres cutover (D-025). SQLite does **not** enforce
foreign keys by default, and the schema relies on them, so a connect-time listener
issues `PRAGMA foreign_keys=ON` for every SQLite connection.

Serverless Postgres (Neon) autosuspends on idle and can drop pooled connections
underneath us, so every engine gets `pool_pre_ping` (liveness check before a
connection is handed out); the hosted PG path also sets `pool_recycle` to retire
connections before Neon's server-side idle timeout does (D-062).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import Connection, make_url

DEFAULT_DATABASE_URL = "sqlite:///data/vja.db"

# Retire a pooled connection after this many idle seconds (non-SQLite only) so it is
# refreshed before Neon's serverless autosuspend drops it server-side. 30 min is well
# under Neon's timeouts while keeping churn negligible at our request volume.
POOL_RECYCLE_SECONDS = 1800


def get_engine(url: str | None = None) -> Engine:
    """Create an Engine for `url` (or `VJA_DATABASE_URL`, or the local SQLite default)."""
    resolved = url or os.environ.get("VJA_DATABASE_URL", DEFAULT_DATABASE_URL)
    # `pool_pre_ping` is safe on every dialect; `pool_recycle` only matters for a
    # networked pool (SQLite's connection is local, so leave it at the default).
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if make_url(resolved).get_backend_name() != "sqlite":
        kwargs["pool_recycle"] = POOL_RECYCLE_SECONDS
    engine = create_engine(resolved, **kwargs)
    if engine.dialect.name == "sqlite":
        _enable_sqlite_foreign_keys(engine)
    return engine


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@contextmanager
def begin(engine: Engine) -> Iterator[Connection]:
    """Transactional connection scope — commits on success, rolls back on exception."""
    with engine.begin() as conn:
        yield conn
