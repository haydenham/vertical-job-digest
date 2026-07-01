"""Engine behavior: SQLite foreign-key enforcement is actually ON (Block 1).

SQLite ignores foreign keys unless `PRAGMA foreign_keys=ON` is set per connection. The
schema relies on FKs, so this verifies the engine's connect-listener does its job — a
posting referencing a non-existent employer must be rejected, not silently stored.

Also pins the serverless-PG connection hardening (D-062): every engine pre-pings, and
the hosted PG path recycles idle connections before Neon's autosuspend drops them.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from vja.db.engine import POOL_RECYCLE_SECONDS, get_engine
from vja.db.schema import postings


def test_sqlite_engine_pre_pings_but_does_not_recycle() -> None:
    # pre_ping is safe/cheap everywhere; recycle is pointless for a local SQLite file,
    # so it stays at SQLAlchemy's -1 (never) default. No connection is opened here.
    engine = get_engine("sqlite:///:memory:")
    assert engine.pool._pre_ping is True
    assert engine.pool._recycle == -1


def test_postgres_engine_pre_pings_and_recycles() -> None:
    # create_engine is lazy — building a PG engine does not connect, so this is offline.
    engine = get_engine("postgresql+psycopg://u:p@localhost:5432/db")
    assert engine.pool._pre_ping is True
    assert engine.pool._recycle == POOL_RECYCLE_SECONDS


def test_foreign_keys_are_enforced(migrated_engine: Engine) -> None:
    now = datetime.now(UTC)
    with pytest.raises(IntegrityError), migrated_engine.begin() as conn:
        conn.execute(
            postings.insert().values(
                employer_id=999_999,  # no such employer
                external_id="x",
                content_hash="h",
                raw_payload={},
                first_seen_at=now,
                last_seen_at=now,
            )
        )
