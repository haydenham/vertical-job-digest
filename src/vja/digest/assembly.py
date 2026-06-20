"""Digest assembly: what changed since the user last heard from us (P3B1, P5.4 rationale).

Builds the digest *contents* for one (vertical, profile) and runs the verification gate
(D-008) over the new ones — it does NOT send anything or write a `digests` row; that's `send.py`.

The digest is **per-profile** (D-027): the `new` set is the postings that, for *this* profile's
resume version, earned a relevant match (verdict `maybe`/`yes`/`strong_yes` — D-037), ordered by
score descending. Out-of-scope/`no` postings carry no relevant match and so drop out; "the diff
is the product" still holds, now filtered to "the diff *worth reading*". Closures are
vertical-global (no rationale).

Window: `since` defaults to the last successfully-sent digest **for this recipient** in the
vertical (`last_sent_at`). When there is none (the first digest), `since is None` → every
currently-relevant open posting is `new` (the baseline) and `closed` is empty.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, cast

from sqlalchemy import Engine, RowMapping, Select, func, select

from vja.db.profiles import Profile
from vja.db.schema import digests, employers, matches, postings
from vja.digest.verification import default_client, verify_apply_url
from vja.models import DigestStatus, PostingStatus, Verdict


@dataclass(frozen=True)
class DigestPosting:
    external_id: str
    company: str
    title: str | None
    location: str | None
    apply_url: str | None
    first_seen_at: datetime
    # Match fields (the rationale) — populated for `new` postings, None/empty for closures.
    verdict: str | None = None
    score: int | None = None
    rationale: str | None = None
    fits: list[str] | None = None
    gaps: list[str] | None = None


@dataclass(frozen=True)
class DigestContents:
    vertical: str
    recipient: str
    since: datetime | None
    generated_at: datetime
    new: list[DigestPosting]
    closed: list[DigestPosting]
    quarantined: list[DigestPosting]


class _Unset:
    """Sentinel so a caller can pass `since=None` (baseline) distinctly from 'auto-resolve'."""


_UNSET: Final = _Unset()

# Verdicts worth surfacing in the digest (D-037): a `no` is honest but not inbox-worthy.
_RELEVANT_VERDICTS: Final = (Verdict.STRONG_YES.value, Verdict.YES.value, Verdict.MAYBE.value)

_POSTING_COLUMNS = (
    postings.c.external_id,
    postings.c.title,
    postings.c.location,
    postings.c.apply_url,
    postings.c.first_seen_at,
    employers.c.name.label("company"),
)

_MATCH_COLUMNS = (
    matches.c.verdict,
    matches.c.score,
    matches.c.rationale,
    matches.c.fits,
    matches.c.gaps,
)


def last_sent_at(engine: Engine, vertical: str, recipient: str) -> datetime | None:
    """The most recent successfully-sent digest time for (`vertical`, `recipient`), or None."""
    stmt = select(func.max(digests.c.sent_at)).where(
        digests.c.vertical == vertical,
        digests.c.recipient == recipient,
        digests.c.status == DigestStatus.SENT.value,
    )
    # The schema's UTCDateTime type already returns tz-aware UTC on every dialect.
    with engine.connect() as conn:
        return cast("datetime | None", conn.execute(stmt).scalar_one_or_none())


def _closed_select() -> Select[Any]:
    return select(*_POSTING_COLUMNS).select_from(
        postings.join(employers, postings.c.employer_id == employers.c.id)
    )


def _new_select(profile: Profile) -> Select[Any]:
    """Open postings INNER-JOINed to this profile's relevant match — gated and score-sortable."""
    return (
        select(*_POSTING_COLUMNS, *_MATCH_COLUMNS)
        .select_from(
            postings.join(employers, postings.c.employer_id == employers.c.id).join(
                matches, matches.c.posting_id == postings.c.id
            )
        )
        .where(
            matches.c.profile_id == profile.id,
            matches.c.resume_version == profile.resume_version,
            matches.c.verdict.in_(_RELEVANT_VERDICTS),
        )
    )


def _loads(value: Any) -> list[str] | None:
    """Parse a `matches` JSON-text list column (`fits`/`gaps`) back into a list."""
    if not value:
        return None
    return cast("list[str]", json.loads(value))


def _to_posting(row: RowMapping, *, with_match: bool) -> DigestPosting:
    return DigestPosting(
        external_id=row["external_id"],
        company=row["company"],
        title=row["title"],
        location=row["location"],
        apply_url=row["apply_url"],
        first_seen_at=row["first_seen_at"],
        verdict=row["verdict"] if with_match else None,
        score=row["score"] if with_match else None,
        rationale=row["rationale"] if with_match else None,
        fits=_loads(row["fits"]) if with_match else None,
        gaps=_loads(row["gaps"]) if with_match else None,
    )


def _fetch(engine: Engine, stmt: Select[Any], *, with_match: bool) -> list[DigestPosting]:
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [_to_posting(row, with_match=with_match) for row in rows]


def build_digest(
    engine: Engine,
    vertical: str,
    *,
    profile: Profile,
    now: datetime | None = None,
    since: datetime | None | _Unset = _UNSET,
    verify: Callable[[str], bool] | None = None,
) -> DigestContents:
    """Assemble the (vertical, profile) digest: relevant matches as `new`, dead links quarantined.

    See the module docstring for the gating + ordering rules.
    """
    generated_at = now or datetime.now(UTC)
    resolved_since = (
        last_sent_at(engine, vertical, profile.user_email) if isinstance(since, _Unset) else since
    )

    new_stmt = _new_select(profile).where(
        employers.c.vertical == vertical,
        postings.c.status == PostingStatus.OPEN.value,
    )
    if resolved_since is not None:
        new_stmt = new_stmt.where(postings.c.first_seen_at > resolved_since)
    new_stmt = new_stmt.order_by(matches.c.score.desc())
    new_candidates = _fetch(engine, new_stmt, with_match=True)

    if resolved_since is None:
        closed = []  # first digest: no prior state to have closed against
    else:
        closed_stmt = (
            _closed_select()
            .where(
                employers.c.vertical == vertical,
                postings.c.status == PostingStatus.CLOSED.value,
                postings.c.closed_at > resolved_since,
            )
            .order_by(postings.c.first_seen_at)
        )
        closed = _fetch(engine, closed_stmt, with_match=False)

    new, quarantined = _apply_verification_gate(new_candidates, verify)

    return DigestContents(
        vertical=vertical,
        recipient=profile.user_email,
        since=resolved_since,
        generated_at=generated_at,
        new=new,
        closed=closed,
        quarantined=quarantined,
    )


def _apply_verification_gate(
    candidates: list[DigestPosting], verify: Callable[[str], bool] | None
) -> tuple[list[DigestPosting], list[DigestPosting]]:
    """Split candidates into (verified, quarantined). A missing/failing link is quarantined."""
    if not candidates:
        return [], []
    if verify is not None:
        return _partition(candidates, verify)
    client = default_client()
    try:
        return _partition(candidates, lambda url: verify_apply_url(url, client))
    finally:
        client.close()


def _partition(
    candidates: list[DigestPosting], check: Callable[[str], bool]
) -> tuple[list[DigestPosting], list[DigestPosting]]:
    verified: list[DigestPosting] = []
    quarantined: list[DigestPosting] = []
    for posting in candidates:
        if posting.apply_url and check(posting.apply_url):
            verified.append(posting)
        else:
            quarantined.append(posting)
    return verified, quarantined
