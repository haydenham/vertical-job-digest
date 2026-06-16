"""Digest assembly: what changed since the user last heard from us (P3B1).

Builds the digest *contents* (new + closed postings for a vertical) and runs the
verification gate (D-008) over the new ones — it does NOT send anything or write a
`digests` row; that's P3B2.

Window: `since` defaults to the last successfully-sent digest for the vertical
(`last_sent_at`). When there is none (the first digest), `since is None` → every
currently-open posting is `new` (the baseline) and `closed` is empty.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, cast

from sqlalchemy import Engine, Select, func, select

from vja.db.schema import digests, employers, postings
from vja.digest.verification import default_client, verify_apply_url
from vja.models import DigestStatus, PostingStatus


@dataclass(frozen=True)
class DigestPosting:
    external_id: str
    company: str
    title: str | None
    location: str | None
    apply_url: str | None
    first_seen_at: datetime


@dataclass(frozen=True)
class DigestContents:
    vertical: str
    since: datetime | None
    generated_at: datetime
    new: list[DigestPosting]
    closed: list[DigestPosting]
    quarantined: list[DigestPosting]


class _Unset:
    """Sentinel so a caller can pass `since=None` (baseline) distinctly from 'auto-resolve'."""


_UNSET: Final = _Unset()

_COLUMNS = (
    postings.c.external_id,
    postings.c.title,
    postings.c.location,
    postings.c.apply_url,
    postings.c.first_seen_at,
    employers.c.name.label("company"),
)


def last_sent_at(engine: Engine, vertical: str) -> datetime | None:
    """The most recent successfully-sent digest time for `vertical`, or None."""
    stmt = select(func.max(digests.c.sent_at)).where(
        digests.c.vertical == vertical,
        digests.c.status == DigestStatus.SENT.value,
    )
    with engine.connect() as conn:
        result = cast("datetime | None", conn.execute(stmt).scalar_one_or_none())
    # SQLite returns naive datetimes; re-attach UTC so the API is consistently tz-aware
    # (we store everything in UTC — `docs/04`). Postgres already returns aware values.
    if result is not None and result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result


def _base_select() -> Select[Any]:
    return select(*_COLUMNS).select_from(
        postings.join(employers, postings.c.employer_id == employers.c.id)
    )


def _fetch(engine: Engine, stmt: Select[Any]) -> list[DigestPosting]:
    with engine.connect() as conn:
        rows = conn.execute(stmt.order_by(postings.c.first_seen_at)).mappings().all()
    return [
        DigestPosting(
            external_id=row["external_id"],
            company=row["company"],
            title=row["title"],
            location=row["location"],
            apply_url=row["apply_url"],
            first_seen_at=row["first_seen_at"],
        )
        for row in rows
    ]


def build_digest(
    engine: Engine,
    vertical: str,
    *,
    now: datetime | None = None,
    since: datetime | None | _Unset = _UNSET,
    verify: Callable[[str], bool] | None = None,
) -> DigestContents:
    """Assemble the digest for `vertical`, with dead apply links quarantined out of `new`."""
    generated_at = now or datetime.now(UTC)
    resolved_since = last_sent_at(engine, vertical) if isinstance(since, _Unset) else since

    new_stmt = _base_select().where(
        employers.c.vertical == vertical,
        postings.c.status == PostingStatus.OPEN.value,
    )
    if resolved_since is not None:
        new_stmt = new_stmt.where(postings.c.first_seen_at > resolved_since)
    new_candidates = _fetch(engine, new_stmt)

    if resolved_since is None:
        closed = []  # first digest: no prior state to have closed against
    else:
        closed_stmt = _base_select().where(
            employers.c.vertical == vertical,
            postings.c.status == PostingStatus.CLOSED.value,
            postings.c.closed_at > resolved_since,
        )
        closed = _fetch(engine, closed_stmt)

    new, quarantined = _apply_verification_gate(new_candidates, verify)

    return DigestContents(
        vertical=vertical,
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
