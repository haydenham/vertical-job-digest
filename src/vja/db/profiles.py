"""profiles repository — the matching profile (resume + domain vocabulary) per (user, vertical).

A profile is the resume the matcher (5.3) reasons against. `resume_version` is a content hash of
the resume text, so editing the resume produces a **new version row** (matches reference the version
they ran against — `docs/04` §4); the prior version is deactivated, never deleted. Loading the same
resume again is idempotent. Recipient/identity migrates off env to here at Phase 5.4 (D-027).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Literal, cast

from sqlalchemy import Connection, Engine, select

from vja.db.engine import begin
from vja.db.schema import profiles, users

# A "running" stamp older than this reads as done — the crash guard (D-082): a killed container
# must not strand the dashboard's "matching in progress" banner forever. Widened 10 → 30 minutes
# (D-101): a backfill matches up to VJA_BACKFILL_MAX_POSTINGS postings one sequential LLM call at
# a time, and production runs took 6-25 minutes, so at 10 the guard was firing on *healthy*
# backfills — telling the user matching had finished while it was still running, and stopping the
# dashboard poll that was the running instance's only traffic. The bound must exceed a real
# backfill, not average it.
BACKFILL_STALE_AFTER = timedelta(minutes=30)

# D-085: first upload is free of this clock; each accepted changed-résumé upload consumes one
# rolling window. Kept as a timedelta so the comparison and Retry-After derive from one value.
RESUME_REUPLOAD_COOLDOWN = timedelta(hours=24)

# The self-serve vertical-switch clock. Deliberately *not* the same clock as the résumé one: a
# switch and a reupload are different actions, and blocking one on the other would trap a new user
# who picked the wrong vertical minutes after uploading. Only a switch that creates real matching
# work consumes it (see `switch_vertical`).
VERTICAL_SWITCH_COOLDOWN = timedelta(hours=24)

BackfillStatus = Literal["running", "done"]

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


@dataclass(frozen=True)
class ProfileUpload:
    """A committed profile change and whether it needs a new background backfill.

    Shared by both write paths — `upload_profile` (a résumé) and `switch_vertical` (the same
    résumé, a different vertical) — because the caller's job is identical either way: schedule
    `run_backfill` iff `backfill_required`.
    """

    profile: Profile
    backfill_required: bool


class ProfileVerticalConflict(RuntimeError):
    """The upload tried to cross the user's immutable one-vertical boundary (D-064)."""

    def __init__(self, vertical: str) -> None:
        self.vertical = vertical
        super().__init__(vertical)


class ResumeReuploadLimited(RuntimeError):
    """A changed résumé arrived before the user's rolling D-085 window reopened."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(retry_after)


class VerticalSwitchLimited(RuntimeError):
    """A work-producing vertical switch arrived before the user's rolling window reopened."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(retry_after)


class NoActiveProfile(RuntimeError):
    """There is no active profile to switch — the caller is signed in but never onboarded."""


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


def _upsert_profile(
    conn: Connection,
    *,
    user_email: str,
    vertical: str,
    version: str,
    resume_text: str,
    domain_vocabulary: Sequence[str],
    user_id: int | None,
    stamp: datetime,
) -> int:
    """Connection-scoped profile upsert shared by CLI loading and the atomic upload path."""
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
        conn.execute(profiles.update().where(profiles.c.id == existing).values(active=1, **link))
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
        return _upsert_profile(
            conn,
            user_email=user_email,
            vertical=vertical,
            version=version,
            resume_text=resume_text,
            domain_vocabulary=domain_vocabulary,
            user_id=user_id,
            stamp=stamp,
        )


def upload_profile(
    engine: Engine,
    *,
    user_id: int,
    user_email: str,
    vertical: str,
    resume_text: str,
    domain_vocabulary: Sequence[str],
    before_backfill: Callable[[], None],
    now: datetime | None = None,
    cooldown: timedelta = RESUME_REUPLOAD_COOLDOWN,
) -> ProfileUpload:
    """Atomically apply the authenticated upload policy (D-064/D-085).

    The user's row is the serialization boundary. Identical extracted text returns the active
    profile unchanged and never calls `before_backfill`. The first changed reupload claims the
    persistent rolling clock; another changed upload before it expires raises with the exact
    Retry-After. Profile versioning, the cooldown claim, and the progress start stamp commit in
    one transaction, including when the upload reactivates a previously used content version.

    `before_backfill` lets the API apply D-057's global budget only after this transaction has
    established that real work is needed, but before any write is made. Raising rolls back cleanly.
    """
    stamp = now or datetime.now(UTC)
    version = resume_version(resume_text)

    with begin(engine) as conn:
        user_row = conn.execute(
            select(users.c.last_resume_reupload_at).where(users.c.id == user_id).with_for_update()
        ).one()
        active_row = (
            conn.execute(
                select(*_PROFILE_COLS)
                .where(profiles.c.user_email == user_email, profiles.c.active == 1)
                .order_by(profiles.c.vertical)
                .with_for_update()
            )
            .mappings()
            .first()
        )

        if active_row is not None:
            active = _row_to_profile(dict(active_row))
            if active.vertical != vertical:
                raise ProfileVerticalConflict(active.vertical)
            if active.resume_version == version:
                return ProfileUpload(profile=active, backfill_required=False)

            last_reupload = cast("datetime | None", user_row.last_resume_reupload_at)
            if last_reupload is not None:
                retry_at = last_reupload + cooldown
                if stamp < retry_at:
                    raise ResumeReuploadLimited(ceil((retry_at - stamp).total_seconds()))

        before_backfill()

        if active_row is not None:
            conn.execute(
                users.update().where(users.c.id == user_id).values(last_resume_reupload_at=stamp)
            )

        profile_id = _upsert_profile(
            conn,
            user_email=user_email,
            vertical=vertical,
            version=version,
            resume_text=resume_text,
            domain_vocabulary=domain_vocabulary,
            user_id=user_id,
            stamp=stamp,
        )
        conn.execute(
            profiles.update().where(profiles.c.id == profile_id).values(backfill_started_at=stamp)
        )
        row = (
            conn.execute(select(*_PROFILE_COLS).where(profiles.c.id == profile_id)).mappings().one()
        )
        return ProfileUpload(profile=_row_to_profile(dict(row)), backfill_required=True)


def switch_vertical(
    engine: Engine,
    *,
    user_id: int,
    user_email: str,
    target_vertical: str,
    domain_vocabulary: Sequence[str],
    before_backfill: Callable[[], None],
    now: datetime | None = None,
    cooldown: timedelta = VERTICAL_SWITCH_COOLDOWN,
) -> ProfileUpload:
    """Move this user's active profile to `target_vertical`, keeping their résumé.

    The self-serve replacement for what used to be a support action. The résumé is never
    re-uploaded — `resume_text` already lives on the profile row, so a switch is "re-file the same
    résumé under a different vertical, with that vertical's domain vocabulary" plus a backfill.

    **The cost model, and why the cooldown is conditional.** Matching is idempotent per
    `(posting, profile, resume_version)` (`db.matches.postings_needing_match`), and
    `_upsert_profile` reactivates the *same* profile row for a `(user, vertical, resume_version)`
    seen before — so the old vertical's matches survive on the deactivated row and returning to it
    re-runs nothing but the remainder. A first visit pays a real backfill and therefore consumes
    the rolling clock; a revisit is near-free and does not. The clock exists to stop one user
    exhausting the *global* daily ceiling (`match.check_backfill_budget`), which would 429 other
    people's signups — it is not there to protect the few dollars.

    Raises `NoActiveProfile` (nothing to switch — that user belongs in onboarding) and
    `VerticalSwitchLimited` (rolling window still closed). `before_backfill` applies the global
    budget guard after the transaction has established that real work is needed but before any
    write, mirroring `upload_profile`; raising rolls back cleanly.
    """
    stamp = now or datetime.now(UTC)

    with begin(engine) as conn:
        user_row = conn.execute(
            select(users.c.last_vertical_switch_at).where(users.c.id == user_id).with_for_update()
        ).one()
        active_row = (
            conn.execute(
                select(*_PROFILE_COLS)
                .where(profiles.c.user_email == user_email, profiles.c.active == 1)
                .order_by(profiles.c.vertical)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if active_row is None:
            raise NoActiveProfile(user_email)

        active = _row_to_profile(dict(active_row))
        if active.vertical == target_vertical:
            return ProfileUpload(profile=active, backfill_required=False)

        # Has this résumé version already been filed under the target vertical? If so the matches
        # from that visit are still on the row and this switch creates almost no work.
        revisit = (
            conn.execute(
                select(profiles.c.id).where(
                    profiles.c.user_email == user_email,
                    profiles.c.vertical == target_vertical,
                    profiles.c.resume_version == active.resume_version,
                )
            ).scalar_one_or_none()
            is not None
        )

        if not revisit:
            last_switch = cast("datetime | None", user_row.last_vertical_switch_at)
            if last_switch is not None:
                retry_at = last_switch + cooldown
                if stamp < retry_at:
                    raise VerticalSwitchLimited(ceil((retry_at - stamp).total_seconds()))

        before_backfill()

        if not revisit:
            conn.execute(
                users.update().where(users.c.id == user_id).values(last_vertical_switch_at=stamp)
            )

        # Deactivate every *other* vertical this user holds. `_upsert_profile` only clears versions
        # within the vertical it is writing, so without this the user would be left active in two
        # verticals at once — breaking the surviving half of D-064 and, worse, making the nightly
        # match them (and bill them) in both.
        conn.execute(
            profiles.update()
            .where(profiles.c.user_email == user_email, profiles.c.vertical != target_vertical)
            .values(active=0)
        )

        profile_id = _upsert_profile(
            conn,
            user_email=user_email,
            vertical=target_vertical,
            version=active.resume_version,
            resume_text=active.resume_text,
            domain_vocabulary=domain_vocabulary,
            user_id=user_id,
            stamp=stamp,
        )
        conn.execute(
            profiles.update().where(profiles.c.id == profile_id).values(backfill_started_at=stamp)
        )
        row = (
            conn.execute(select(*_PROFILE_COLS).where(profiles.c.id == profile_id)).mappings().one()
        )
        return ProfileUpload(profile=_row_to_profile(dict(row)), backfill_required=True)


def get_profile(engine: Engine, profile_id: int) -> Profile | None:
    """The profile by id, or None — the upload endpoint loads the just-upserted row to hand the
    backfill a `Profile` object (D-057)."""
    stmt = select(*_PROFILE_COLS).where(profiles.c.id == profile_id)
    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().one_or_none()
    return _row_to_profile(dict(row)) if row is not None else None


def active_profiles(engine: Engine, vertical: str) -> list[Profile]:
    """The active matching profiles for `vertical` (drives nightly matching in 5.3)."""
    stmt = select(*_PROFILE_COLS).where(profiles.c.vertical == vertical, profiles.c.active == 1)
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [_row_to_profile(dict(row)) for row in rows]


def mark_backfill_started(engine: Engine, profile_id: int, *, now: datetime | None = None) -> None:
    """Stamp `backfill_started_at` (D-082). The upload endpoint calls this *before* scheduling the
    background task, so the SPA's immediate post-202 `/api/me` probe already sees `running` —
    stamping only inside `run_backfill` would race the probe. Idempotent overwrite."""
    with begin(engine) as conn:
        conn.execute(
            profiles.update()
            .where(profiles.c.id == profile_id)
            .values(backfill_started_at=now or datetime.now(UTC))
        )


def mark_backfill_completed(
    engine: Engine, profile_id: int, *, now: datetime | None = None
) -> None:
    """Stamp `backfill_completed_at` (D-082) — `run_backfill` calls this on exit, including when
    every candidate failed (per-posting isolation means the run itself still finished)."""
    with begin(engine) as conn:
        conn.execute(
            profiles.update()
            .where(profiles.c.id == profile_id)
            .values(backfill_completed_at=now or datetime.now(UTC))
        )


def backfill_stamps(engine: Engine, profile_id: int) -> tuple[datetime | None, datetime | None]:
    """(started_at, completed_at) for the profile — the raw inputs to `derive_backfill_status`."""
    stmt = select(profiles.c.backfill_started_at, profiles.c.backfill_completed_at).where(
        profiles.c.id == profile_id
    )
    with engine.connect() as conn:
        row = conn.execute(stmt).one_or_none()
    return (row[0], row[1]) if row is not None else (None, None)


def derive_backfill_status(
    started: datetime | None,
    completed: datetime | None,
    *,
    now: datetime,
    stale_after: timedelta = BACKFILL_STALE_AFTER,
) -> BackfillStatus | None:
    """running/done/None from the two stamps (D-082), computed server-side so the client stays dumb.

    Ordering matters: a same-résumé reupload reactivates a row whose `completed_at` is from the
    *previous* backfill, so `completed >= started` (not mere presence) is what means done. A fresh
    `started` with no newer `completed` is running — unless it is older than `stale_after`, which
    reads as done (the crash guard). Both stamps absent (pre-D-082 rows, CLI-only profiles) → None.
    """
    if started is None:
        return "done" if completed is not None else None
    if completed is not None and completed >= started:
        return "done"
    return "running" if now - started < stale_after else "done"


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
