"""matches repository — selecting match candidates and persisting the rationale (`docs/04` §5).

A *candidate* is an open, already-extracted posting that has no `matches` row yet for a given
(profile, resume_version). Stage A (title scope) and Stage B (the `prefilter` over the extracted
fields) are applied by the caller (`vja.match.run_matching`) — this query only bounds the set to
open ∧ extracted ∧ not-yet-matched, so the strong model never re-runs on a posting it already
judged for this resume version (idempotency; mirrors `postings_needing_extraction`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, delete, exists, func, select
from sqlalchemy.engine import Connection

from vja.db.engine import begin
from vja.db.postings import activity_window_clause, age_floor_clause
from vja.db.schema import employers, matches, postings
from vja.models import MatchTrigger


@dataclass(frozen=True)
class MatchCandidate:
    """An open, extracted, unmatched posting + the structured fields the matcher reasons over."""

    posting_id: int
    title: str | None
    level: str | None
    location: str | None
    remote: str | None
    work_auth: str | None
    stack: list[str]
    comp_min: int | None
    comp_max: int | None
    comp_raw: str | None


def postings_needing_match(
    engine: Engine,
    vertical: str,
    profile_id: int,
    resume_version: str,
    *,
    now: datetime,
    since: datetime | None = None,
) -> list[MatchCandidate]:
    """Open, extracted postings for `vertical` with no match yet for (profile, resume_version).

    Stage A/B filtering is the caller's job — this just excludes postings already matched against
    this resume version, so a re-run only matches the new/unmatched remainder (D-005 cost).

    `since` bounds the set to the recency window (`activity_window_clause`) for the signup
    backfill's 5-day cap (D-024/D-039); the default `None` is the nightly path, which is
    date-uncapped *within* the age floor below.

    **The age floor (`age_floor_clause(now)`) applies on every path, and it is the one gate here
    that saves money rather than spending it.** A posting past `max_posting_age_days()` cannot be
    displayed on the dashboard or mailed in a digest, so paying the strong model to reason about
    it buys nothing — this is the first place in the project where LLM spend falls by declining to
    ask the question. It is a no-op on the backfill path, whose 5-day `since` is already stricter.

    Ordered freshest-first so that callers which *count*-cap the result truncate a defined set.
    """
    already_matched = (
        select(matches.c.id)
        .where(
            matches.c.posting_id == postings.c.id,
            matches.c.profile_id == profile_id,
            matches.c.resume_version == resume_version,
        )
        .correlate(postings)
    )
    stmt = (
        select(
            postings.c.id,
            postings.c.title,
            postings.c.level,
            postings.c.location,
            postings.c.remote,
            postings.c.work_auth,
            postings.c.stack,
            postings.c.comp_min,
            postings.c.comp_max,
            postings.c.comp_raw,
        )
        .select_from(postings.join(employers, postings.c.employer_id == employers.c.id))
        .where(
            employers.c.vertical == vertical,
            postings.c.status == "open",
            postings.c.extracted_at.is_not(None),
            ~exists(already_matched),
            age_floor_clause(now),
        )
    )
    if since is not None:
        stmt = stmt.where(activity_window_clause(since))
    # Freshest first, and deterministic (D-103). Both callers that cap the result
    # (`run_backfill`'s D-057 guard, and the D-103 per-run pipeline cap) truncate this list, so
    # without an ORDER BY they were slicing a set the database was free to return in any order —
    # meaning which postings got matched, and which were silently dropped, was undefined. Newest
    # first is also the product-correct priority when the cap does bite (D-039).
    stmt = stmt.order_by(postings.c.first_seen_at.desc(), postings.c.id.desc())
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        MatchCandidate(
            posting_id=row["id"],
            title=row["title"],
            level=row["level"],
            location=row["location"],
            remote=row["remote"],
            work_auth=row["work_auth"],
            stack=list(row["stack"] or []),
            comp_min=row["comp_min"],
            comp_max=row["comp_max"],
            comp_raw=row["comp_raw"],
        )
        for row in rows
    ]


def count_matches_since(
    engine: Engine, since: datetime, *, trigger: MatchTrigger | None = None
) -> int:
    """Number of `matches` rows created at/after `since` — the spend proxy for the daily ceiling.

    No per-match cost is stored (only `pipeline_runs.llm_cost_usd`, which the backfill doesn't
    write), so the cost guard (D-057) estimates spend from the match count × a nominal per-match
    cost. `trigger` narrows the count to one origin; the ceiling passes `BACKFILL` because it
    governs *signup* spend, and the nightly it would otherwise count is uncapped by design and was
    never gated by it (D-101). Unfiltered (the default) counts every trigger.
    """
    stmt = select(func.count()).select_from(matches).where(matches.c.created_at >= since)
    if trigger is not None:
        stmt = stmt.where(matches.c.trigger == trigger.value)
    with engine.connect() as conn:
        return int(conn.execute(stmt).scalar_one())


def delete_matches_failing_scope(engine: Engine, vertical: str) -> int:
    """Delete matches whose posting is no longer in-scope (`in_scope IS NOT TRUE`) for `vertical`.

    The D-043 corpus-repair step: a posting matched while the location gate was blind (a foreign or
    out-of-level role) now fails Stage B, so its rationale is stale and must go — the corrected gate
    keeps `vja-match` from recreating it. Returns the row count deleted. Idempotent (a second run
    finds none).
    """
    failing = (
        select(postings.c.id)
        .select_from(postings.join(employers, postings.c.employer_id == employers.c.id))
        .where(employers.c.vertical == vertical, postings.c.in_scope.is_not(True))
    )
    with begin(engine) as conn:
        result = conn.execute(delete(matches).where(matches.c.posting_id.in_(failing)))
    return result.rowcount or 0


def save_match(
    conn: Connection,
    posting_id: int,
    profile_id: int,
    resume_version: str,
    columns: dict[str, Any],
    *,
    model: str,
    trigger: str,
    now: datetime,
) -> None:
    """Insert one `matches` row (the rationale) for (posting, profile, resume_version)."""
    conn.execute(
        matches.insert().values(
            posting_id=posting_id,
            profile_id=profile_id,
            resume_version=resume_version,
            model_version=model,
            trigger=trigger,
            created_at=now,
            **columns,
        )
    )
