"""Postings repository — the read/write operations the diff job needs (`docs/04` §3).

Each function takes an already-open `Connection` and does NOT manage its own transaction;
the caller (`vja.pipeline.sync_employer`) wraps a whole employer's changes in one
transaction so a partial write can't leave the diff half-applied. Postings are never
deleted — vanished ones are marked `closed` (D-009).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, Engine, and_, case, func, select
from sqlalchemy.engine import Connection

from vja.db.schema import employers, matches, postings
from vja.models import RELEVANT_VERDICTS, AtsType, Employer, PostingStatus, RawPosting


def activity_window_clause(cutoff: datetime) -> ColumnElement[bool]:
    """The D-030/D-024 freshness predicate: the most-recent ATS activity date is within the
    window, falling back to our detection date (`first_seen_at`) when the ATS gave no date.

    One home for the `COALESCE(source_updated_at, first_seen_at) >= cutoff` logic — shared by
    the dashboard window query (`open_postings_with_match_quality`) and the backfill candidate
    selection (`postings_needing_match(since=...)`). Mirrors the dashboard's "posted *or* updated
    within the window" rule (D-030).
    """
    return func.coalesce(postings.c.source_updated_at, postings.c.first_seen_at) >= cutoff


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


def closed_index(conn: Connection, employer_id: int) -> dict[str, str]:
    """`{external_id: content_hash}` for this employer's currently-closed postings.

    The diff sees a reappeared posting as "new" (it's absent from the open index), but a row
    already exists for its `(employer_id, external_id)` — inserting would violate the UNIQUE
    constraint. The caller intersects `diff.new` with this set to route a reappeared posting to
    `reopen_posting` instead of `insert_posting`; the stored hash lets it tell a content-changed
    reopen from an identical one (so extraction is only invalidated when the body actually moved).
    """
    rows = conn.execute(
        select(postings.c.external_id, postings.c.content_hash).where(
            postings.c.employer_id == employer_id,
            postings.c.status == PostingStatus.CLOSED.value,
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


def reopen_posting(
    conn: Connection,
    employer_id: int,
    posting: RawPosting,
    content_hash: str,
    now: datetime,
    *,
    source_updated_at: datetime | None = None,
    content_changed: bool,
) -> None:
    """Resurrect a previously-`closed` posting that reappeared in a fetch (D-009 lifecycle).

    A closed row is never deleted, so a reappeared posting can't be re-inserted (UNIQUE
    `(employer_id, external_id)`); we update the existing row in place. **`first_seen_at` is reset
    to `now`** so the role re-enters the digest's `new` set (which keys on
    `first_seen_at > last_sent_at`) and the dashboard's "new today" — a role that's open again is
    freshly actionable. `source_updated_at` is written only when non-None (same guard as
    `bump_last_seen` — never null a previously-good date). When `content_changed`, `extracted_at`/
    `extraction_model` are cleared so Layer-2 re-extracts against the new body (mirrors
    `update_changed`); the stale extracted fields + `in_scope` are left until that re-extraction
    overwrites them. When the body is identical, the cached extraction is preserved (D-035).
    """
    values: dict[str, Any] = {
        "content_hash": content_hash,
        "raw_payload": posting.raw,
        "apply_url": posting.apply_url,
        "title": posting.title,
        "location": posting.location,
        "status": PostingStatus.OPEN.value,
        "closed_at": None,
        "first_seen_at": now,
        "last_seen_at": now,
    }
    if source_updated_at is not None:
        values["source_updated_at"] = source_updated_at
    if content_changed:
        values["extracted_at"] = None
        values["extraction_model"] = None
    conn.execute(
        postings.update()
        .where(postings.c.employer_id == employer_id, postings.c.external_id == posting.external_id)
        .values(**values)
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
    """An open, not-yet-extracted posting + its employer (for the Workday detail fetch, P5.2).

    `location` is the current stored L1 location, carried so the caller can compute the durable
    `in_scope` gate against the *effective* (L1-authoritative) location, not the model's read.
    """

    posting_id: int
    external_id: str
    title: str | None
    location: str | None
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
            postings.c.location,
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
            location=row["location"],
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

    Two extracted columns are **L1-authoritative** — they fill only when the existing value is NULL
    and never overwrite a non-null L1 value, because the fetcher's structured field is more reliable
    than the model's best-effort body read:
    - `location`: the L1 location (e.g. Workday `locationsText` = "Mumbai, India") is set at insert;
      Haiku often returns null for it, and an unconditional write blanked it — which left Stage B
      and the matcher blind to geography. Extraction now only fills `location` when L1 left it null.
    - `source_updated_at`: the normalized extracted `posted_at` (D-038), filled only when L1 gave no
      date (Workday) so a clean L1 `updated_at` survives.
    """
    values = dict(columns)
    if "location" in values:
        values["location"] = case(
            (postings.c.location.is_(None), values["location"]),
            else_=postings.c.location,
        )
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


@dataclass(frozen=True)
class RepairRow:
    """A posting's fields for the one-time corpus repair (D-043): re-derive `location` from the
    captured `raw_payload`, recompute `in_scope`, then drop stale matches. `extracted` gates whether
    `in_scope` is (re)computed — the gate only means anything once the structured fields exist."""

    posting_id: int
    ats_type: AtsType
    raw_payload: dict[str, Any]
    level: str | None
    location: str | None
    extracted: bool


def postings_for_repair(engine: Engine, vertical: str) -> list[RepairRow]:
    """Every employer-backed posting for `vertical` + the fields the corpus repair needs (D-043)."""
    stmt = (
        select(
            postings.c.id,
            employers.c.ats_type,
            postings.c.raw_payload,
            postings.c.level,
            postings.c.location,
            postings.c.extracted_at,
        )
        .select_from(postings.join(employers, postings.c.employer_id == employers.c.id))
        .where(employers.c.vertical == vertical)
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        RepairRow(
            posting_id=row["id"],
            ats_type=AtsType(row["ats_type"]),
            raw_payload=row["raw_payload"] or {},
            level=row["level"],
            location=row["location"],
            extracted=row["extracted_at"] is not None,
        )
        for row in rows
    ]


def apply_location_repair(
    conn: Connection, posting_id: int, *, location: str | None, in_scope: bool | None
) -> None:
    """Write a re-derived L1 `location` and/or recomputed `in_scope` for one posting (D-043 repair).

    `location` is passed only when it actually changed (the caller keeps the L1-authoritative rule:
    a re-derived non-null L1 value wins; a null L1 leaves the existing value — possibly a model
    fill — untouched). `in_scope` is passed only for extracted postings (`None` ⇒ leave it NULL).
    A call with neither is a no-op.
    """
    values: dict[str, Any] = {}
    if location is not None:
        values["location"] = location
    if in_scope is not None:
        values["in_scope"] = in_scope
    if values:
        conn.execute(postings.update().where(postings.c.id == posting_id).values(**values))


@dataclass(frozen=True)
class DashboardPosting:
    """One row for the read-only dashboard (P6 B1, D-041/D-043): an in-scope open posting plus this
    profile's match quality (`None` when not yet assessed).

    The dashboard's universe is the durable **in-scope** set — open postings with `in_scope IS TRUE`
    (the persisted Stage-A+B gate, D-043), so out-of-scope and out-of-US/level roles never surface.
    Match fields come from a LEFT JOIN keyed on `(profile_id, resume_version)`, so unassessed rows
    carry `None`. The *Cleaned* view returns every in-scope role incl. `no`; *Matched* keeps only
    relevant verdicts (D-045).
    """

    posting_id: int
    company: str
    title: str | None
    location: str | None
    apply_url: str | None
    first_seen_at: datetime
    source_updated_at: datetime | None
    # Extracted compensation (F2 Phase A, D-087). Carried raw — the API layer decides whether the
    # integers are safe to render as a range (`vja.comp`), because `comp_raw` is the only thing
    # that corroborates them.
    comp_min: int | None
    comp_max: int | None
    comp_raw: str | None
    # Match quality for this (profile, resume_version) — None when unassessed (LEFT JOIN miss).
    verdict: str | None
    score: int | None
    fits: list[str] | None
    gaps: list[str] | None
    rationale: str | None


def _loads(value: Any) -> list[str] | None:
    """Parse a `matches` JSON-text list column (`fits`/`gaps`) back into a list."""
    if not value:
        return None
    return cast("list[str]", json.loads(value))


def open_postings_with_match_quality(
    engine: Engine,
    vertical: str,
    profile_id: int,
    resume_version: str,
    *,
    cutoff: datetime | None,
    by_first_seen: bool = False,
    cleaned: bool = False,
) -> list[DashboardPosting]:
    """In-scope open postings for `vertical`, LEFT-joined to this profile's match (P6 B1, D-043).

    Two orthogonal axes (the API maps query params onto them):
    - **recency** via the caller-computed `cutoff`: `None` → all open; `by_first_seen=True` →
      window on `first_seen_at` only (the *New today* basis = our detection date, mirroring the
      digest; D-030); else `activity_window_clause(cutoff)` (posted *or* updated within, with the
      `first_seen_at` fallback) — the *This week* / *Two weeks* toggles.
    - **view** (`cleaned`): the *Matched* view (default, `cleaned=False`) returns only this résumé's
      relevant matches (`strong_yes`/`yes`/`maybe`) — the AI's recommendation subset. The *Cleaned*
      view (`cleaned=True`) is the whole in-scope US-software universe — every verdict incl. `no`
      and not-yet-assessed (objective job list, same set for any profile; match columns decorate).
      (D-045)

    Floor is always the durable in-scope set (`in_scope IS TRUE`, D-043) — out-of-scope and
    out-of-US/level roles never appear. Newest-activity-first (D-010).
    """
    freshness = func.coalesce(postings.c.source_updated_at, postings.c.first_seen_at)
    match_join = and_(
        matches.c.posting_id == postings.c.id,
        matches.c.profile_id == profile_id,
        matches.c.resume_version == resume_version,
    )
    stmt = (
        select(
            postings.c.id.label("posting_id"),
            employers.c.name.label("company"),
            postings.c.title,
            postings.c.location,
            postings.c.apply_url,
            postings.c.first_seen_at,
            postings.c.source_updated_at,
            postings.c.comp_min,
            postings.c.comp_max,
            postings.c.comp_raw,
            matches.c.verdict,
            matches.c.score,
            matches.c.fits,
            matches.c.gaps,
            matches.c.rationale,
        )
        .select_from(
            postings.join(employers, postings.c.employer_id == employers.c.id).outerjoin(
                matches, match_join
            )
        )
        .where(
            employers.c.vertical == vertical,
            postings.c.status == PostingStatus.OPEN.value,
            postings.c.in_scope.is_(True),
        )
        .order_by(freshness.desc())
    )
    if cutoff is not None:
        in_window = (
            postings.c.first_seen_at >= cutoff if by_first_seen else activity_window_clause(cutoff)
        )
        stmt = stmt.where(in_window)
    if (
        not cleaned
    ):  # *Matched* view: only this résumé's relevant verdicts (excludes `no` + unassessed)
        stmt = stmt.where(matches.c.verdict.in_(RELEVANT_VERDICTS))
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        DashboardPosting(
            posting_id=row["posting_id"],
            company=row["company"],
            title=row["title"],
            location=row["location"],
            apply_url=row["apply_url"],
            first_seen_at=row["first_seen_at"],
            source_updated_at=row["source_updated_at"],
            comp_min=row["comp_min"],
            comp_max=row["comp_max"],
            comp_raw=row["comp_raw"],
            verdict=row["verdict"],
            score=row["score"],
            fits=_loads(row["fits"]),
            gaps=_loads(row["gaps"]),
            rationale=row["rationale"],
        )
        for row in rows
    ]
