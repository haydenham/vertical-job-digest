"""Integration tests for the `digests` repository (P3B2).

Real migrated SQLite. Pins the row lifecycle: a `pending` row carries the contents JSON,
`mark_sent` stamps `sent_at` + flips to `sent`, `mark_failed` records the error + flips to
`failed`. (`sent_at` on a `sent` row is what advances the next digest's window — see
`test_digest_send.test_successful_send_advances_the_window`.)
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select

from vja.db import digests as digests_repo
from vja.db.engine import begin
from vja.db.schema import digests

_CONTENTS = {"vertical": "grid_power_software", "new": [{"external_id": "a"}], "closed": []}


def _row(engine: Engine, digest_id: int) -> dict[str, Any]:
    with engine.connect() as conn:
        return dict(conn.execute(select(digests).where(digests.c.id == digest_id)).mappings().one())


def test_create_pending_stores_contents_and_pending_status(migrated_engine: Engine) -> None:
    with begin(migrated_engine) as conn:
        digest_id = digests_repo.create_pending(
            conn, recipient="me@example.com", vertical="grid_power_software", contents=_CONTENTS
        )
    row = _row(migrated_engine, digest_id)
    assert row["status"] == "pending"
    assert row["recipient"] == "me@example.com"
    assert row["sent_at"] is None
    assert row["error"] is None
    assert row["contents"] == _CONTENTS


def test_mark_sent_sets_status_and_sent_at(migrated_engine: Engine) -> None:
    sent_at = datetime(2026, 6, 17, 9, 0, tzinfo=UTC)
    with begin(migrated_engine) as conn:
        digest_id = digests_repo.create_pending(
            conn, recipient="me@example.com", vertical="grid_power_software", contents=_CONTENTS
        )
    with begin(migrated_engine) as conn:
        digests_repo.mark_sent(conn, digest_id, sent_at=sent_at)
    row = _row(migrated_engine, digest_id)
    assert row["status"] == "sent"
    assert row["sent_at"] == sent_at
    assert row["error"] is None


def test_mark_failed_records_error_and_leaves_sent_at_null(migrated_engine: Engine) -> None:
    with begin(migrated_engine) as conn:
        digest_id = digests_repo.create_pending(
            conn, recipient="me@example.com", vertical="grid_power_software", contents=_CONTENTS
        )
    with begin(migrated_engine) as conn:
        digests_repo.mark_failed(conn, digest_id, error="Resend returned 422: bad domain")
    row = _row(migrated_engine, digest_id)
    assert row["status"] == "failed"
    assert row["error"] == "Resend returned 422: bad domain"
    assert row["sent_at"] is None
