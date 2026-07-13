"""Integration tests for the profiles repository (P5.1).

Real migrated SQLite. Pins: a resume loads as one active profile keyed on a content-hash version;
re-loading the same resume is idempotent; editing the resume makes a new active version and
deactivates the prior one; `active_profiles` returns only the current one.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, select

from vja.db.profiles import (
    BACKFILL_STALE_AFTER,
    active_profile_for_user,
    active_profiles,
    backfill_stamps,
    derive_backfill_status,
    mark_backfill_completed,
    mark_backfill_started,
    resume_version,
    upsert_profile,
)
from vja.db.schema import profiles


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


def test_derive_backfill_status_completed_only_is_done() -> None:
    """A completed stamp with no started (CLI backfill on a pre-stamp row) still reads done."""
    assert derive_backfill_status(None, _T0, now=_T0 + timedelta(minutes=1)) == "done"
