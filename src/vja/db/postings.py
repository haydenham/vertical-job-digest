"""Postings repository — the read/write operations the diff job needs (`docs/04` §3).

Each function takes an already-open `Connection` and does NOT manage its own transaction;
the caller (`vja.pipeline.sync_employer`) wraps a whole employer's changes in one
transaction so a partial write can't leave the diff half-applied. Postings are never
deleted — vanished ones are marked `closed` (D-009).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Connection

from vja.db.schema import postings
from vja.models import PostingStatus, RawPosting


def open_index(conn: Connection, employer_id: int) -> dict[str, str]:
    """`{external_id: content_hash}` for this employer's currently-open postings.

    Feeds both the diff (its keys are the stored-open id set) and the content-change
    check (compare a still-present posting's new hash against the stored one) in one query.
    """
    rows = conn.execute(
        select(postings.c.external_id, postings.c.content_hash).where(
            postings.c.employer_id == employer_id,
            postings.c.status == PostingStatus.OPEN.value,
        )
    ).all()
    return {external_id: content_hash for external_id, content_hash in rows}


def insert_posting(
    conn: Connection,
    employer_id: int,
    posting: RawPosting,
    content_hash: str,
    now: datetime,
) -> None:
    """Insert a newly-seen posting as `open` with `first_seen = last_seen = now`."""
    conn.execute(
        postings.insert().values(
            employer_id=employer_id,
            external_id=posting.external_id,
            content_hash=content_hash,
            raw_payload=posting.raw,
            apply_url=posting.apply_url,
            title=posting.title,
            location=posting.location,
            status=PostingStatus.OPEN.value,
            first_seen_at=now,
            last_seen_at=now,
        )
    )


def bump_last_seen(conn: Connection, employer_id: int, external_id: str, now: datetime) -> None:
    """Mark a still-present, unchanged posting as seen again."""
    conn.execute(
        postings.update()
        .where(postings.c.employer_id == employer_id, postings.c.external_id == external_id)
        .values(last_seen_at=now)
    )


def update_changed(
    conn: Connection,
    employer_id: int,
    external_id: str,
    content_hash: str,
    raw_payload: dict[str, Any],
    now: datetime,
) -> None:
    """A still-present posting whose content changed: refresh hash + payload + last_seen.

    Extracted fields are intentionally left as-is; re-running Layer-2 extraction off the
    new `content_hash` is a later block's concern.
    """
    conn.execute(
        postings.update()
        .where(postings.c.employer_id == employer_id, postings.c.external_id == external_id)
        .values(content_hash=content_hash, raw_payload=raw_payload, last_seen_at=now)
    )


def close_posting(conn: Connection, employer_id: int, external_id: str, now: datetime) -> None:
    """Mark a vanished posting `closed` (never delete — D-009)."""
    conn.execute(
        postings.update()
        .where(postings.c.employer_id == employer_id, postings.c.external_id == external_id)
        .values(status=PostingStatus.CLOSED.value, closed_at=now)
    )
