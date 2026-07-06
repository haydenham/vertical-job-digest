"""Integration tests for the profiles repository (P5.1).

Real migrated SQLite. Pins: a resume loads as one active profile keyed on a content-hash version;
re-loading the same resume is idempotent; editing the resume makes a new active version and
deactivates the prior one; `active_profiles` returns only the current one.
"""

from sqlalchemy import Engine, func, select

from vja.db.profiles import (
    active_profile_for_user,
    active_profiles,
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
