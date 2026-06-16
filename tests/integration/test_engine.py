"""Engine behavior: SQLite foreign-key enforcement is actually ON (Block 1).

SQLite ignores foreign keys unless `PRAGMA foreign_keys=ON` is set per connection. The
schema relies on FKs, so this verifies the engine's connect-listener does its job — a
posting referencing a non-existent employer must be rejected, not silently stored.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from vja.db.schema import postings


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
