"""digests repository — the auditable record of exactly what we shipped (`docs/04` §6).

Lifecycle mirrors `pipeline_runs`: a `pending` row carrying the full `contents` JSON is written
*before* the send, then finalized to `sent` (with `sent_at`) or `failed` (with `error`). Persisting
contents up front means a crash mid-send leaves a visible record of what was about to ship, and a
failed send is itself a durable alert. Both functions take an open `Connection`; the caller commits
each in its own transaction so the `pending` row is durable before the network call.

`sent_at` on a `sent` row is what `digest.assembly.last_sent_at` keys the next digest's window off —
so finalizing a successful send automatically advances the diff window.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.engine import Connection

from vja.db.schema import digests
from vja.models import DigestStatus


def create_pending(
    conn: Connection, *, recipient: str, vertical: str, contents: dict[str, Any]
) -> int:
    """Insert a `pending` digest row (status defaults to pending) and return its id."""
    result = conn.execute(
        digests.insert().values(
            recipient=recipient,
            vertical=vertical,
            status=DigestStatus.PENDING.value,
            contents=contents,
        )
    )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def mark_sent(conn: Connection, digest_id: int, *, sent_at: datetime) -> None:
    """Finalize a digest as successfully sent at `sent_at`."""
    conn.execute(
        digests.update()
        .where(digests.c.id == digest_id)
        .values(status=DigestStatus.SENT.value, sent_at=sent_at)
    )


def mark_failed(conn: Connection, digest_id: int, *, error: str) -> None:
    """Finalize a digest as failed, recording `error` (a failed send is itself an alert)."""
    conn.execute(
        digests.update()
        .where(digests.c.id == digest_id)
        .values(status=DigestStatus.FAILED.value, error=error)
    )
