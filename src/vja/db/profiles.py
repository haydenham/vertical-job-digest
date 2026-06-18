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


@dataclass(frozen=True)
class Profile:
    id: int
    user_email: str
    vertical: str
    resume_version: str
    resume_text: str
    domain_vocabulary: tuple[str, ...]


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
    now: datetime | None = None,
) -> int:
    """Idempotently load a resume as the active profile for (user, vertical); return its id.

    Same resume text → same `resume_version` → no-op (re-activated if needed). A changed resume →
    a new active version row, with prior versions for this (user, vertical) deactivated.
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

        if existing is not None:
            conn.execute(profiles.update().where(profiles.c.id == existing).values(active=1))
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
            )
        )
        pk = result.inserted_primary_key
        assert pk is not None
        return int(pk[0])


def active_profiles(engine: Engine, vertical: str) -> list[Profile]:
    """The active matching profiles for `vertical` (drives nightly matching in 5.3)."""
    stmt = select(
        profiles.c.id,
        profiles.c.user_email,
        profiles.c.vertical,
        profiles.c.resume_version,
        profiles.c.resume_text,
        profiles.c.domain_vocabulary,
    ).where(profiles.c.vertical == vertical, profiles.c.active == 1)
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        Profile(
            id=row["id"],
            user_email=row["user_email"],
            vertical=row["vertical"],
            resume_version=row["resume_version"],
            resume_text=row["resume_text"],
            domain_vocabulary=tuple(cast("list[str]", row["domain_vocabulary"] or [])),
        )
        for row in rows
    ]
