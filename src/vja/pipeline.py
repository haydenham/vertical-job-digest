"""The per-employer diff job: fetch → diff → persist (`docs/04` lifecycle).

`sync_employer` is the conductor that ties the existing pieces together for ONE employer:
the fetcher (Chunks 4–5), `compute_diff` (Chunk 6), `content_hash` (Chunk 3), and the
postings repository (Block 2). The loop over all employers + the `pipeline_runs`
run-summary is a later block.

THE GUARD (the project's highest-stakes rule): if the fetch raises `FetchError`, we
return a `failed` result and touch **nothing** — never run the diff, never close a
posting. A transient failure must not be read as "this employer has zero open jobs"
(that would close every posting and ship a digest claiming the company's jobs all died).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine

from vja.db import postings as postings_repo
from vja.db.engine import begin
from vja.diff import compute_diff
from vja.fetchers.base import Fetcher, FetchError
from vja.hashing import content_hash
from vja.models import Employer, RawPosting


@dataclass(frozen=True)
class SyncResult:
    """Outcome of syncing one employer."""

    employer_id: int
    status: str  # "ok" | "failed"
    new: int = 0
    closed: int = 0
    updated: int = 0
    unchanged: int = 0
    error: str | None = None


def _hash(posting: RawPosting) -> str:
    return content_hash(
        title=posting.title,
        location=posting.location,
        description=posting.description,
    )


def sync_employer(
    engine: Engine,
    employer: Employer,
    fetcher: Fetcher,
    *,
    now: datetime | None = None,
) -> SyncResult:
    """Fetch, diff against stored-open postings, and persist the changes for one employer."""
    stamp = now or datetime.now(UTC)

    # --- THE GUARD: a failed fetch makes zero changes ------------------------------
    try:
        fetched = fetcher.fetch(employer)
    except FetchError as exc:
        return SyncResult(employer_id=employer.id, status="failed", error=str(exc))

    by_id = {posting.external_id: posting for posting in fetched}

    with begin(engine) as conn:
        stored = postings_repo.open_index(conn, employer.id)
        diff = compute_diff(by_id.keys(), stored.keys())

        for external_id in diff.new:
            posting = by_id[external_id]
            postings_repo.insert_posting(conn, employer.id, posting, _hash(posting), stamp)

        updated = 0
        for external_id in diff.still_present:
            posting = by_id[external_id]
            new_hash = _hash(posting)
            if new_hash != stored[external_id]:
                postings_repo.update_changed(
                    conn, employer.id, external_id, new_hash, posting.raw, stamp
                )
                updated += 1
            else:
                postings_repo.bump_last_seen(conn, employer.id, external_id, stamp)

        for external_id in diff.closed:
            postings_repo.close_posting(conn, employer.id, external_id, stamp)

    return SyncResult(
        employer_id=employer.id,
        status="ok",
        new=len(diff.new),
        closed=len(diff.closed),
        updated=updated,
        unchanged=len(diff.still_present) - updated,
    )
