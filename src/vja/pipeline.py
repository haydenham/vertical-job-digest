"""The diff job: fetch → diff → persist, per employer and across the universe.

`sync_employer` is the conductor for ONE employer, tying together the fetcher (Chunks 4–5),
`compute_diff` (Chunk 6), `content_hash` (Chunk 3), and the postings repository (Block 2).
`run_pipeline` (Block 3) runs it over every active fetchable employer and records a
`pipeline_runs` summary.

THE GUARD (the project's highest-stakes rule): if the fetch raises `FetchError`, we
return a `failed` result and touch **nothing** — never run the diff, never close a
posting. A transient failure must not be read as "this employer has zero open jobs"
(that would close every posting and ship a digest claiming the company's jobs all died).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine

from vja.dates import normalize_ats_date
from vja.db import pipeline_runs as pipeline_runs_repo
from vja.db import postings as postings_repo
from vja.db.employers import active_fetchable_employers
from vja.db.engine import begin, get_engine
from vja.diff import compute_diff
from vja.fetchers.base import Fetcher, FetchError
from vja.fetchers.registry import get_fetcher
from vja.hashing import content_hash
from vja.models import AtsType, Employer, PipelineRunStatus, RawPosting


@dataclass(frozen=True)
class SyncResult:
    """Outcome of syncing one employer."""

    employer_id: int
    status: str  # "ok" | "failed"
    new: int = 0
    reopened: int = 0
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

        # A "new" id (absent from the open index) may already exist as a *closed* row — a
        # posting that vanished, then reappeared. It must be reopened in place, not inserted
        # (UNIQUE(employer_id, external_id) — D-009 never deletes the closed row).
        previously_closed = postings_repo.closed_index(conn, employer.id)
        reopened = 0
        for external_id in diff.new:
            posting = by_id[external_id]
            new_hash = _hash(posting)
            source_updated_at = normalize_ats_date(posting.updated_at)
            if external_id in previously_closed:
                postings_repo.reopen_posting(
                    conn,
                    employer.id,
                    posting,
                    new_hash,
                    stamp,
                    source_updated_at=source_updated_at,
                    content_changed=new_hash != previously_closed[external_id],
                )
                reopened += 1
            else:
                postings_repo.insert_posting(
                    conn,
                    employer.id,
                    posting,
                    new_hash,
                    stamp,
                    source_updated_at=source_updated_at,
                )

        updated = 0
        for external_id in diff.still_present:
            posting = by_id[external_id]
            source_updated_at = normalize_ats_date(posting.updated_at)
            new_hash = _hash(posting)
            if new_hash != stored[external_id]:
                postings_repo.update_changed(
                    conn,
                    employer.id,
                    external_id,
                    new_hash,
                    posting.raw,
                    stamp,
                    source_updated_at=source_updated_at,
                )
                updated += 1
            else:
                postings_repo.bump_last_seen(
                    conn, employer.id, external_id, stamp, source_updated_at=source_updated_at
                )

        for external_id in diff.closed:
            postings_repo.close_posting(conn, employer.id, external_id, stamp)

    return SyncResult(
        employer_id=employer.id,
        status="ok",
        new=len(diff.new) - reopened,
        reopened=reopened,
        closed=len(diff.closed),
        updated=updated,
        unchanged=len(diff.still_present) - updated,
    )


@dataclass(frozen=True)
class RunSummary:
    """Outcome of a whole pipeline run (mirrors the persisted `pipeline_runs` row)."""

    run_id: int
    status: str  # "ok" | "partial" | "failed"
    employers_fetched: int
    fetch_failures: int
    postings_new: int
    postings_reopened: int
    postings_closed: int
    results: list[SyncResult]
    errors: list[dict[str, Any]]


def _run_status(*, total: int, failures: int) -> PipelineRunStatus:
    if failures == 0:
        return PipelineRunStatus.OK  # incl. the zero-employer case
    if failures == total:
        return PipelineRunStatus.FAILED
    return PipelineRunStatus.PARTIAL


def run_pipeline(
    engine: Engine,
    vertical: str | None = None,
    *,
    now: datetime | None = None,
    resolve_fetcher: Callable[[AtsType], Fetcher] = get_fetcher,
) -> RunSummary:
    """Run fetch→diff→persist over every active fetchable employer; record a `pipeline_runs` row.

    `resolve_fetcher` is injected (defaults to the real registry) so tests can supply fakes.
    Each employer is isolated: an unexpected exception is recorded and the loop continues, so
    one bad employer can never abort the whole run.
    """
    stamp = now or datetime.now(UTC)

    # Commit the `running` row before the loop so a mid-run crash leaves a visible tombstone.
    with begin(engine) as conn:
        run_id = pipeline_runs_repo.start_run(conn, stamp)

    employers = active_fetchable_employers(engine, vertical)
    results: list[SyncResult] = []
    errors: list[dict[str, Any]] = []

    for employer in employers:
        try:
            fetcher = resolve_fetcher(employer.ats_type)
            result = sync_employer(engine, employer, fetcher, now=stamp)
        except (
            Exception
        ) as exc:  # deliberate per-employer isolation boundary (recorded, not swallowed)
            results.append(SyncResult(employer_id=employer.id, status="failed", error=repr(exc)))
            errors.append({"employer_id": employer.id, "name": employer.name, "error": repr(exc)})
            continue
        results.append(result)
        if result.status == "failed":
            errors.append(
                {"employer_id": employer.id, "name": employer.name, "error": result.error}
            )

    failures = sum(1 for result in results if result.status == "failed")
    status = _run_status(total=len(results), failures=failures)
    postings_new = sum(result.new for result in results)
    postings_reopened = sum(result.reopened for result in results)
    postings_closed = sum(result.closed for result in results)
    finished = now or datetime.now(UTC)

    with begin(engine) as conn:
        pipeline_runs_repo.finish_run(
            conn,
            run_id,
            status=status,
            employers_fetched=len(results),
            fetch_failures=failures,
            postings_new=postings_new,
            postings_closed=postings_closed,
            errors=errors,
            now=finished,
        )

    return RunSummary(
        run_id=run_id,
        status=status.value,
        employers_fetched=len(results),
        fetch_failures=failures,
        postings_new=postings_new,
        postings_reopened=postings_reopened,
        postings_closed=postings_closed,
        results=results,
        errors=errors,
    )


def run_main(argv: list[str] | None = None) -> int:
    """CLI: `vja-run [--vertical V]` — run the pipeline against the default DB."""
    parser = argparse.ArgumentParser(
        prog="vja-run", description="Run the nightly fetch→diff→persist pipeline."
    )
    parser.add_argument("--vertical", default=None, help="limit to one vertical (default: all)")
    args = parser.parse_args(argv)

    summary = run_pipeline(get_engine(), args.vertical)
    print(
        f"run {summary.run_id}: status={summary.status} "
        f"employers={summary.employers_fetched} failures={summary.fetch_failures} "
        f"new={summary.postings_new} reopened={summary.postings_reopened} "
        f"closed={summary.postings_closed}"
    )
    for err in summary.errors:
        print(f"  ! {err['name']}: {err['error']}")
    return 1 if summary.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(run_main())
