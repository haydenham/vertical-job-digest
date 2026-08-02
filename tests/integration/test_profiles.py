"""Integration tests for the profiles repository (P5.1).

Real migrated SQLite. Pins: a resume loads as one active profile keyed on a content-hash version;
re-loading the same resume is idempotent; editing the resume makes a new active version and
deactivates the prior one; `active_profiles` returns only the current one.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import Engine, func, select

from vja.db.profiles import (
    BACKFILL_STALE_AFTER,
    VERTICAL_SWITCH_COOLDOWN,
    NoActiveProfile,
    ProfileUpload,
    VerticalSwitchLimited,
    active_profile_for_user,
    active_profiles,
    backfill_stamps,
    derive_backfill_status,
    mark_backfill_completed,
    mark_backfill_started,
    resume_version,
    switch_vertical,
    upsert_profile,
)
from vja.db.schema import profiles, users
from vja.db.users import upsert_user_by_google


def _count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(profiles)).scalar_one())


def _load(engine: Engine, text: str) -> int:
    return upsert_profile(
        engine,
        user_email="me@example.com",
        vertical="grid_power_software",
        resume_text=text,
        domain_vocabulary=["power markets", "DER"],
    )


def test_upsert_creates_one_active_versioned_profile(migrated_engine: Engine) -> None:
    pid = _load(migrated_engine, "RESUME ONE")

    assert _count(migrated_engine) == 1
    actives = active_profiles(migrated_engine, "grid_power_software")
    assert len(actives) == 1
    p = actives[0]
    assert p.id == pid
    assert p.resume_version == resume_version("RESUME ONE")
    assert p.resume_text == "RESUME ONE"
    assert p.domain_vocabulary == ("power markets", "DER")


def test_reupsert_same_resume_is_idempotent(migrated_engine: Engine) -> None:
    first = _load(migrated_engine, "RESUME ONE")
    again = _load(migrated_engine, "RESUME ONE")

    assert first == again
    assert _count(migrated_engine) == 1  # no duplicate row


def test_changed_resume_makes_new_active_version(migrated_engine: Engine) -> None:
    _load(migrated_engine, "RESUME ONE")
    second = _load(migrated_engine, "RESUME TWO (edited)")

    assert _count(migrated_engine) == 2  # both versions retained (matches reference versions)
    actives = active_profiles(migrated_engine, "grid_power_software")
    assert len(actives) == 1  # only the latest is active
    assert actives[0].id == second
    assert actives[0].resume_version == resume_version("RESUME TWO (edited)")


def test_active_profiles_isolates_vertical(migrated_engine: Engine) -> None:
    _load(migrated_engine, "RESUME ONE")  # grid_power_software
    upsert_profile(
        migrated_engine,
        user_email="me@example.com",
        vertical="aviation_software",
        resume_text="AVIATION RESUME",
        domain_vocabulary=[],
    )
    assert len(active_profiles(migrated_engine, "grid_power_software")) == 1
    assert len(active_profiles(migrated_engine, "aviation_software")) == 1


def test_active_profile_for_user_returns_the_one(migrated_engine: Engine) -> None:
    """The SPA-routing query: a user's single active profile across verticals (D-064)."""
    pid = _load(migrated_engine, "RESUME ONE")
    prof = active_profile_for_user(migrated_engine, "me@example.com")
    assert prof is not None
    assert prof.id == pid
    assert prof.vertical == "grid_power_software"


def test_active_profile_for_user_none_when_absent(migrated_engine: Engine) -> None:
    assert active_profile_for_user(migrated_engine, "nobody@example.com") is None


def test_active_profile_for_user_ignores_deactivated(migrated_engine: Engine) -> None:
    """After a résumé update the prior version is inactive; the query returns only the active."""
    _load(migrated_engine, "RESUME ONE")
    second = _load(migrated_engine, "RESUME TWO (edited)")
    prof = active_profile_for_user(migrated_engine, "me@example.com")
    assert prof is not None
    assert prof.id == second


# --- backfill status stamps + derivation (D-082) ----------------------------------------------

_T0 = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def test_backfill_stamps_roundtrip(migrated_engine: Engine) -> None:
    """Both stamps write independently and read back tz-aware; unstamped rows read (None, None)."""
    pid = _load(migrated_engine, "RESUME ONE")
    assert backfill_stamps(migrated_engine, pid) == (None, None)

    mark_backfill_started(migrated_engine, pid, now=_T0)
    assert backfill_stamps(migrated_engine, pid) == (_T0, None)

    done = _T0 + timedelta(minutes=2)
    mark_backfill_completed(migrated_engine, pid, now=done)
    assert backfill_stamps(migrated_engine, pid) == (_T0, done)


def test_derive_backfill_status_unstamped_is_none() -> None:
    """Pre-D-082 rows / CLI-seeded profiles never stamped anything → no status at all."""
    assert derive_backfill_status(None, None, now=_T0) is None


def test_derive_backfill_status_fresh_start_is_running() -> None:
    assert derive_backfill_status(_T0, None, now=_T0 + timedelta(minutes=1)) == "running"


def test_derive_backfill_status_completed_after_start_is_done() -> None:
    assert (
        derive_backfill_status(_T0, _T0 + timedelta(minutes=2), now=_T0 + timedelta(minutes=3))
        == "done"
    )


def test_derive_backfill_status_reupload_ordering_is_running() -> None:
    """The reupload race (D-082): a same-résumé reupload reactivates a row whose completed_at is
    from the PREVIOUS backfill. completed < started must read running, not done."""
    old_completed = _T0 - timedelta(days=3)
    assert derive_backfill_status(_T0, old_completed, now=_T0 + timedelta(minutes=1)) == "running"


def test_derive_backfill_status_stale_running_reads_done() -> None:
    """The crash guard: a started-but-never-completed run older than the staleness window must not
    strand the dashboard banner."""
    now = _T0 + BACKFILL_STALE_AFTER + timedelta(seconds=1)
    assert derive_backfill_status(_T0, None, now=now) == "done"


def test_derive_backfill_status_long_running_backfill_still_reads_running() -> None:
    """The D-101 regression: the crash guard must outlast a *healthy* backfill.

    A signup matches up to VJA_BACKFILL_MAX_POSTINGS postings one sequential LLM call at a time;
    production runs took 6-25 minutes. At the old 10-minute window every run past 10 minutes was
    declared done while it was still working, so the dashboard told the user matching had finished,
    showed them a partial list, and stopped the poll that was the running instance's only traffic.
    """
    assert derive_backfill_status(_T0, None, now=_T0 + timedelta(minutes=25)) == "running"


def test_derive_backfill_status_completed_only_is_done() -> None:
    """A completed stamp with no started (CLI backfill on a pre-stamp row) still reads done."""
    assert derive_backfill_status(None, _T0, now=_T0 + timedelta(minutes=1)) == "done"


# --- self-serve vertical switching -------------------------------------------------------------
# The switch re-files the user's *existing* résumé under a new vertical (no re-upload) and hands
# the caller a backfill flag. The cost model is the load-bearing part: matching is idempotent per
# (posting, profile, resume_version), so returning to a vertical this résumé already visited
# re-runs nothing — and therefore must not consume the rolling clock.

_OTHER = "aviation_software"


def _switch(
    engine: Engine,
    target: str,
    *,
    now: datetime | None = None,
    user_id: int = 1,
    before_backfill: Callable[[], None] = lambda: None,
) -> ProfileUpload:
    return switch_vertical(
        engine,
        user_id=user_id,
        user_email="me@example.com",
        target_vertical=target,
        domain_vocabulary=["avionics"],
        before_backfill=before_backfill,
        now=now,
    )


def _switch_clock(engine: Engine, user_id: int) -> datetime | None:
    with engine.connect() as conn:
        stamp = conn.execute(
            select(users.c.last_vertical_switch_at).where(users.c.id == user_id)
        ).scalar_one()
    return cast("datetime | None", stamp)


def _onboard(engine: Engine, text: str = "RESUME ONE") -> int:
    """A user row plus an active grid profile — the state every switch test starts from."""
    user = upsert_user_by_google(engine, google_sub="g-me", email="me@example.com", name="Me")
    _load(engine, text)
    return user.id


def test_switch_moves_the_active_profile_and_keeps_the_resume(migrated_engine: Engine) -> None:
    uid = _onboard(migrated_engine)

    result = _switch(migrated_engine, _OTHER, now=_T0, user_id=uid)

    assert result.backfill_required
    assert result.profile.vertical == _OTHER
    # Same résumé, so the same version — which is exactly why the matches stay reusable.
    assert result.profile.resume_text == "RESUME ONE"
    assert result.profile.resume_version == resume_version("RESUME ONE")
    assert result.profile.domain_vocabulary == ("avionics",)
    active = active_profile_for_user(migrated_engine, "me@example.com")
    assert active is not None and active.vertical == _OTHER


def test_switch_deactivates_the_old_vertical(migrated_engine: Engine) -> None:
    """The one-active-profile rule has to survive the switch.

    `_upsert_profile` only clears other *versions within the vertical it writes*, so without the
    explicit deactivation the user would be left active in both — which breaks `/api/me` routing
    and, worse, makes the nightly match (and bill) them in two verticals at once.
    """
    uid = _onboard(migrated_engine)
    _switch(migrated_engine, _OTHER, now=_T0, user_id=uid)

    assert active_profiles(migrated_engine, "grid_power_software") == []
    assert len(active_profiles(migrated_engine, _OTHER)) == 1


def test_switch_to_same_vertical_is_a_noop(migrated_engine: Engine) -> None:
    uid = _onboard(migrated_engine)

    result = _switch(migrated_engine, "grid_power_software", now=_T0, user_id=uid)

    assert not result.backfill_required
    assert _switch_clock(migrated_engine, uid) is None  # no work, no clock


def test_switch_without_a_profile_raises(migrated_engine: Engine) -> None:
    user = upsert_user_by_google(migrated_engine, google_sub="g-me", email="me@example.com")
    with pytest.raises(NoActiveProfile):
        _switch(migrated_engine, _OTHER, now=_T0, user_id=user.id)


def test_first_visit_consumes_the_clock_and_blocks_the_next(migrated_engine: Engine) -> None:
    uid = _onboard(migrated_engine)
    _switch(migrated_engine, _OTHER, now=_T0, user_id=uid)
    assert _switch_clock(migrated_engine, uid) == _T0

    # Back to grid is a revisit (free, below); on to a *third* vertical is new work and blocked.
    _switch(migrated_engine, "grid_power_software", now=_T0 + timedelta(minutes=1), user_id=uid)
    with pytest.raises(VerticalSwitchLimited) as excinfo:
        _switch(migrated_engine, "robotics_software", now=_T0 + timedelta(hours=1), user_id=uid)

    # Retry-After is the remainder of the 24h window, as whole seconds.
    assert excinfo.value.retry_after == int(timedelta(hours=23).total_seconds())


def test_clock_reopens_after_the_cooldown(migrated_engine: Engine) -> None:
    uid = _onboard(migrated_engine)
    _switch(migrated_engine, _OTHER, now=_T0, user_id=uid)

    later = _T0 + VERTICAL_SWITCH_COOLDOWN
    result = _switch(migrated_engine, "robotics_software", now=later, user_id=uid)

    assert result.profile.vertical == "robotics_software"
    assert _switch_clock(migrated_engine, uid) == later


def test_revisit_is_free_and_does_not_consume_the_clock(migrated_engine: Engine) -> None:
    """The cost model, pinned.

    Grid → aviation → grid. The return trip reactivates the *same* profile row the first grid
    visit created, so its matches (keyed on posting/profile/resume_version) are all still valid and
    the backfill re-runs nothing. A near-free switch must not spend the user's one daily window,
    and must not be blocked by it either.
    """
    uid = _onboard(migrated_engine)
    grid_before = active_profile_for_user(migrated_engine, "me@example.com")
    assert grid_before is not None

    _switch(migrated_engine, _OTHER, now=_T0, user_id=uid)
    back = _switch(
        migrated_engine, "grid_power_software", now=_T0 + timedelta(hours=1), user_id=uid
    )

    # Same row id as before the round trip: the prior matches attach to it and survive.
    assert back.profile.id == grid_before.id
    # The clock still reads the aviation switch, untouched by the free return.
    assert _switch_clock(migrated_engine, uid) == _T0


def test_before_backfill_rejection_rolls_everything_back(migrated_engine: Engine) -> None:
    """The budget hook runs after the decision but before any write — a raise leaves no trace."""
    uid = _onboard(migrated_engine)

    def refuse() -> None:
        raise RuntimeError("over budget")

    with pytest.raises(RuntimeError, match="over budget"):
        _switch(migrated_engine, _OTHER, now=_T0, user_id=uid, before_backfill=refuse)

    active = active_profile_for_user(migrated_engine, "me@example.com")
    assert active is not None and active.vertical == "grid_power_software"
    assert _switch_clock(migrated_engine, uid) is None
    assert active_profiles(migrated_engine, _OTHER) == []
