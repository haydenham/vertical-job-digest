"""Postings repository — the read/write operations the diff job needs (`docs/04` §3).

Each function takes an already-open `Connection` and does NOT manage its own transaction;
the caller (`vja.pipeline.sync_employer`) wraps a whole employer's changes in one
transaction so a partial write can't leave the diff half-applied. Postings are never
deleted — vanished ones are marked `closed` (D-009).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, case, select
from sqlalchemy.engine import Connection

from vja.db.schema import employers, postings
from vja.models import AtsType, Employer, PostingStatus, RawPosting


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
    *,
    source_updated_at: datetime | None = None,
) -> None:
    """Insert a newly-seen posting as `open` with `first_seen = last_seen = now`.

    `source_updated_at` is the caller-normalized L1 activity date (D-038), `None` for a source
    that gives no date (Workday) — extraction fills it later via `save_extraction`.
    """
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
            source_updated_at=source_updated_at,
        )
    )


def bump_last_seen(
    conn: Connection,
    employer_id: int,
    external_id: str,
    now: datetime,
    *,
    source_updated_at: datetime | None = None,
) -> None:
    """Mark a still-present, unchanged posting as seen again.

    `source_updated_at` is the diff key (D-016) but not part of `content_hash`, so an ATS
    `updated_at` bump with an unchanged body lands here — refresh it so "updated within window"
    (D-030) stays accurate. Only written when non-None: never null out a previously-good date
    (incl. Workday's extraction-filled one). This is also what self-heals the existing corpus.
    """
    values: dict[str, Any] = {"last_seen_at": now}
    if source_updated_at is not None:
        values["source_updated_at"] = source_updated_at
    conn.execute(
        postings.update()
        .where(postings.c.employer_id == employer_id, postings.c.external_id == external_id)
        .values(**values)
    )


def update_changed(
    conn: Connection,
    employer_id: int,
    external_id: str,
    content_hash: str,
    raw_payload: dict[str, Any],
    now: datetime,
    *,
    source_updated_at: datetime | None = None,
) -> None:
    """A still-present posting whose content changed: refresh hash + payload + last_seen.

    Also clears `extracted_at` so Layer-2 extraction re-runs against the new content next pass
    (the cache-invalidation seam, P5.2). The stale extracted fields are left in place until that
    re-extraction overwrites them — avoids a transient window where level/location read NULL.
    `source_updated_at` is refreshed only when non-None (same rule as `bump_last_seen`).
    """
    values: dict[str, Any] = {
        "content_hash": content_hash,
        "raw_payload": raw_payload,
        "last_seen_at": now,
        "extracted_at": None,
        "extraction_model": None,
    }
    if source_updated_at is not None:
        values["source_updated_at"] = source_updated_at
    conn.execute(
        postings.update()
        .where(postings.c.employer_id == employer_id, postings.c.external_id == external_id)
        .values(**values)
    )


def close_posting(conn: Connection, employer_id: int, external_id: str, now: datetime) -> None:
    """Mark a vanished posting `closed` (never delete — D-009)."""
    conn.execute(
        postings.update()
        .where(postings.c.employer_id == employer_id, postings.c.external_id == external_id)
        .values(status=PostingStatus.CLOSED.value, closed_at=now)
    )


@dataclass(frozen=True)
class ExtractionCandidate:
    """An open, not-yet-extracted posting + its employer (for the Workday detail fetch, P5.2)."""

    posting_id: int
    external_id: str
    title: str | None
    raw_payload: dict[str, Any]
    employer: Employer


def postings_needing_extraction(engine: Engine, vertical: str) -> list[ExtractionCandidate]:
    """Open postings for `vertical` with no extraction yet (`extracted_at IS NULL`).

    The free Stage-A scope filter is applied by the caller (`vja.extract.run_extraction`) on the
    title — this query just bounds the set to open + unextracted, so the LLM only ever sees the
    in-scope, uncached remainder (D-005).
    """
    stmt = (
        select(
            postings.c.id,
            postings.c.external_id,
            postings.c.title,
            postings.c.raw_payload,
            employers.c.id.label("employer_id"),
            employers.c.vertical,
            employers.c.name,
            employers.c.ats_type,
            employers.c.ats_slug,
            employers.c.endpoint,
            employers.c.careers_url,
        )
        .select_from(postings.join(employers, postings.c.employer_id == employers.c.id))
        .where(
            employers.c.vertical == vertical,
            postings.c.status == PostingStatus.OPEN.value,
            postings.c.extracted_at.is_(None),
        )
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        ExtractionCandidate(
            posting_id=row["id"],
            external_id=row["external_id"],
            title=row["title"],
            raw_payload=row["raw_payload"] or {},
            employer=Employer(
                id=row["employer_id"],
                vertical=row["vertical"],
                name=row["name"],
                ats_type=AtsType(row["ats_type"]),
                ats_slug=row["ats_slug"],
                endpoint=row["endpoint"],
                careers_url=row["careers_url"],
            ),
        )
        for row in rows
    ]


def save_extraction(
    conn: Connection,
    posting_id: int,
    columns: dict[str, Any],
    *,
    model: str,
    now: datetime,
    source_updated_at: datetime | None = None,
) -> None:
    """Persist extracted fields + stamp `extraction_model` / `extracted_at` on a posting (P5.2).

    `source_updated_at` is the normalized extracted `posted_at` (D-038). It fills the column **only
    when it's still NULL** — i.e. L1 gave no date (Workday) — so a clean L1 `updated_at` is never
    overwritten by the model's best-effort body-read date (the L1-authoritative rule).
    """
    values = dict(columns)
    if source_updated_at is not None:
        values["source_updated_at"] = case(
            (postings.c.source_updated_at.is_(None), source_updated_at),
            else_=postings.c.source_updated_at,
        )
    conn.execute(
        postings.update()
        .where(postings.c.id == posting_id)
        .values(**values, extraction_model=model, extracted_at=now)
    )
