"""profiles repository — the matching profile (resume + domain vocabulary) per (user, vertical).

A profile is the resume the matcher (5.3) reasons against. `resume_version` is a content hash of
the resume text, so editing the resume produces a **new version row** (matches reference the version
they ran against — `docs/04` §4); the prior version is deactivated, never deleted. Loading the same
resume again is idempotent. Recipient/identity migrates off env to here at Phase 5.4 (D-027).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Engine, select

from vja.db.engine import begin
from vja.db.schema import profiles

_PROFILE_COLS = (
    profiles.c.id,
    profiles.c.user_email,
    profiles.c.vertical,
    profiles.c.resume_version,
    profiles.c.resume_text,
    profiles.c.domain_vocabulary,
)


@dataclass(frozen=True)
class Profile:
    id: int
    user_email: str
    vertical: str
    resume_version: str
    resume_text: str
    domain_vocabulary: tuple[str, ...]


def _row_to_profile(row: dict[str, object]) -> Profile:
    return Profile(
        id=cast("int", row["id"]),
        user_email=cast("str", row["user_email"]),
        vertical=cast("str", row["vertical"]),
        resume_version=cast("str", row["resume_version"]),
        resume_text=cast("str", row["resume_text"]),
        domain_vocabulary=tuple(cast("list[str]", row["domain_vocabulary"] or [])),
    )


def resume_version(resume_text: str) -> str:
    """A stable short content hash of the resume — auto-bumps whenever the resume changes."""
    return hashlib.sha256(resume_text.encode("utf-8")).hexdigest()[:12]


def upsert_profile(
    engine: Engine,
    *,
    user_email: str,
    vertical: str,
    resume_text: str,
    domain_vocabulary: Sequence[str],
    user_id: int | None = None,
    now: datetime | None = None,
) -> int:
    """Idempotently load a resume as the active profile for (user, vertical); return its id.

    Same resume text → same `resume_version` → no-op (re-activated if needed). A changed resume →
    a new active version row, with prior versions for this (user, vertical) deactivated.

    `user_id` links the profile to the authenticated `users` row (D-055) — the upload path passes
    the logged-in user's id (stamped on the new/reactivated row). The CLI loader omits it, leaving
    `user_id` NULL to be backfilled by email on first login, exactly as before (D-055).
    """
    version = resume_version(resume_text)
    stamp = now or datetime.now(UTC)

    with begin(engine) as conn:
        existing = conn.execute(
            select(profiles.c.id).where(
                profiles.c.user_email == user_email,
                profiles.c.vertical == vertical,
                profiles.c.resume_version == version,
            )
        ).scalar_one_or_none()

        # Any other version for this (user, vertical) is no longer the active one.
        conn.execute(
            profiles.update()
            .where(profiles.c.user_email == user_email, profiles.c.vertical == vertical)
            .values(active=0)
        )

        # Only set user_id when supplied (don't clobber an existing link via the CLI path).
        link = {"user_id": user_id} if user_id is not None else {}

        if existing is not None:
            conn.execute(
                profiles.update().where(profiles.c.id == existing).values(active=1, **link)
            )
            return int(existing)

        result = conn.execute(
            profiles.insert().values(
                user_email=user_email,
                vertical=vertical,
                resume_version=version,
                resume_text=resume_text,
                domain_vocabulary=list(domain_vocabulary),
                active=1,
                created_at=stamp,
                **link,
            )
        )
        pk = result.inserted_primary_key
        assert pk is not None
        return int(pk[0])


def get_profile(engine: Engine, profile_id: int) -> Profile | None:
    """The profile by id, or None — the upload endpoint loads the just-upserted row to hand the
    backfill a `Profile` object (D-057)."""
    stmt = select(*_PROFILE_COLS).where(profiles.c.id == profile_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().one_or_none()
    return _row_to_profile(dict(row)) if row is not None else None


def active_verticals(engine: Engine) -> list[str]:
    """Distinct verticals with at least one active profile (drives the dashboard's vertical
    picker so the frontend never hardcodes a slug — D-042). Sorted for a stable default pick."""
    stmt = (
        select(profiles.c.vertical)
        .where(profiles.c.active == 1)
        .distinct()
        .order_by(profiles.c.vertical)
    )
    with engine.connect() as conn:
        return [row[0] for row in conn.execute(stmt).all()]


def active_profiles(engine: Engine, vertical: str) -> list[Profile]:
    """The active matching profiles for `vertical` (drives nightly matching in 5.3)."""
    stmt = select(*_PROFILE_COLS).where(profiles.c.vertical == vertical, profiles.c.active == 1)
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [_row_to_profile(dict(row)) for row in rows]


def active_profile_for_user(engine: Engine, user_email: str) -> Profile | None:
    """This user's single active profile across all verticals, or None (D-064: one per user).

    The source of truth the SPA routes on (`/api/me`) — it answers "what's *my* vertical?" so the
    dashboard never guesses from a global picker. One-vertical-per-user means at most one row; a
    lingering pre-B-4 dual-profile anomaly returns a stable first (ordered) rather than raising, so
    a stray legacy row can't 500 the session probe."""
    stmt = (
        select(*_PROFILE_COLS)
        .where(profiles.c.user_email == user_email, profiles.c.active == 1)
        .order_by(profiles.c.vertical)
    )
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().first()
    return _row_to_profile(dict(row)) if row is not None else None
