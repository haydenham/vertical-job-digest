"""Database engine + connection helpers.

The DB URL comes from `VJA_DATABASE_URL` (default local SQLite); it is the single
thing that changes for the Postgres cutover (D-025). SQLite does **not** enforce
foreign keys by default, and the schema relies on them, so a connect-time listener
issues `PRAGMA foreign_keys=ON` for every SQLite connection.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import Connection

DEFAULT_DATABASE_URL = "sqlite:///data/vja.db"


def get_engine(url: str | None = None) -> Engine:
    """Create an Engine for `url` (or `VJA_DATABASE_URL`, or the local SQLite default)."""
    resolved = url or os.environ.get("VJA_DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = create_engine(resolved)
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
