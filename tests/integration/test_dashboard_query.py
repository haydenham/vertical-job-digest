"""Integration tests for the dashboard query (P6 B1 / D-041 / D-043) — migrated SQLite.

Pins `open_postings_with_match_quality`: the **in-scope floor** (`in_scope IS TRUE`; out-of-scope
rows never appear), the **view axis** (matched-default + relevant-only; `cleaned=True` widens to the
whole in-scope universe incl. `None`-match rows; rejected `no` never shown in either view), and the
**recency axis** (the `COALESCE(source_updated_at, first_seen_at)` activity basis with its
`first_seen_at` fallback, the first_seen-only "new today" basis, all-open) — with newest-first
ordering, vertical scoping, and open-only filtering.

Since D-109 there is a second unconditional floor beside `in_scope`: the **age floor**, which the
recency axis cannot switch off. `now` is passed explicitly (never read off the wall clock) so the
floor is evaluated against the same instant these fixtures are dated from.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select

from vja.db.engine import begin
from vja.db.matches import save_match
from vja.db.postings import open_postings_with_match_quality
from vja.db.profiles import Profile, active_profiles, upsert_profile
from vja.db.schema import employers, postings

_NOW = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
_MIDNIGHT = datetime(2026, 6, 21, 0, 0, tzinfo=UTC)
_WEEK = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)  # _NOW − 7d
_TWO_WEEKS = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)  # _NOW − 14d
_VERTICAL = "grid_power_software"
_EMAIL = "me@example.com"


def _employer(engine: Engine, *, vertical: str = _VERTICAL, name: str = "GridCo") -> int:
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical=vertical,
                name=name,
                ats_type="greenhouse",
                ats_slug=name.lower(),
                source="manual",
                status="active",
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _posting(
    engine: Engine,
    employer_id: int,
    title: str,
    *,
    first_seen: datetime,
    source_updated: datetime | None = None,
    status: str = "open",
    in_scope: bool = True,
    comp_min: int | None = None,
    comp_max: int | None = None,
    comp_raw: str | None = None,
) -> int:
    """Insert a posting. `in_scope` toggles the durable Stage-A+B floor (`in_scope IS TRUE`)."""
    with begin(engine) as conn:
        result = conn.execute(
            postings.insert().values(
                employer_id=employer_id,
                external_id=title,
                content_hash=f"h-{title}",
                raw_payload={},
                title=title,
                apply_url=f"https://example.com/{title}",
                status=status,
                first_seen_at=first_seen,
                last_seen_at=first_seen,
                source_updated_at=source_updated,
                extracted_at=first_seen,
                in_scope=in_scope,
                comp_min=comp_min,
                comp_max=comp_max,
                comp_raw=comp_raw,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _profile(engine: Engine, *, vertical: str = _VERTICAL, email: str = _EMAIL) -> Profile:
    upsert_profile(
        engine, user_email=email, vertical=vertical, resume_text="resume", domain_vocabulary=[]
    )
    return next(p for p in active_profiles(engine, vertical) if p.user_email == email)


def _match(engine: Engine, posting_id: int, profile: Profile, *, verdict: str, score: int) -> None:
    with begin(engine) as conn:
        save_match(
            conn,
            posting_id,
            profile.id,
            profile.resume_version,
            {"verdict": verdict, "score": score, "fits": "[]", "gaps": "[]", "rationale": "ok"},
            model="claude-sonnet-4-6",
            trigger="nightly",
            now=_NOW,
        )


def _titles(rows: list[object]) -> list[str]:
    return [r.title for r in rows]  # type: ignore[attr-defined]


def _query(engine: Engine, profile: Profile, **kwargs: object) -> list[object]:
    # `now` defaults to the module clock so the D-109 age floor is evaluated against the same
    # instant the fixtures are dated from; a test that cares about the floor passes its own.
    kwargs.setdefault("now", _NOW)
    return open_postings_with_match_quality(  # type: ignore[return-value]
        engine,
        _VERTICAL,
        profile.id,
        profile.resume_version,
        **kwargs,  # type: ignore[arg-type]
    )


# --- view axis (Matched / Cleaned) + in-scope floor ----------------------------------------------


def _seed_tiers(engine: Engine) -> Profile:
    """matched(yes), rejected(no), unassessed(in-scope, no match), out_of_scope(in_scope=False)."""
    prof = _profile(engine)
    emp = _employer(engine)
    matched = _posting(engine, emp, "matched", first_seen=_NOW)
    rejected = _posting(engine, emp, "rejected", first_seen=_NOW)
    _posting(engine, emp, "unassessed", first_seen=_NOW)
    _posting(engine, emp, "out_of_scope", first_seen=_NOW, in_scope=False)
    _match(engine, matched, prof, verdict="yes", score=70)
    _match(engine, rejected, prof, verdict="no", score=10)
    return prof


def test_default_is_matched_relevant_only(migrated_engine: Engine) -> None:
    prof = _seed_tiers(migrated_engine)
    rows = _query(migrated_engine, prof, cutoff=None)
    assert _titles(rows) == ["matched"]
    assert rows[0].verdict == "yes"  # type: ignore[attr-defined]
    assert rows[0].score == 70  # type: ignore[attr-defined]


def test_cleaned_view_is_the_whole_in_scope_set_incl_rejected(migrated_engine: Engine) -> None:
    # Cleaned = the objective US-software list: every in-scope verdict incl. `no` and unassessed
    # (D-045). Only `out_of_scope` (in_scope=False) is excluded.
    prof = _seed_tiers(migrated_engine)
    rows = _query(migrated_engine, prof, cutoff=None, cleaned=True)
    assert set(_titles(rows)) == {"matched", "rejected", "unassessed"}
    un = next(r for r in rows if r.title == "unassessed")  # type: ignore[attr-defined]
    assert un.verdict is None and un.score is None  # type: ignore[attr-defined]


def test_rejected_shown_in_cleaned_hidden_in_matched(migrated_engine: Engine) -> None:
    prof = _seed_tiers(migrated_engine)
    assert "rejected" not in _titles(_query(migrated_engine, prof, cutoff=None))  # matched hides it
    assert "rejected" in _titles(  # cleaned shows it (the objective list)
        _query(migrated_engine, prof, cutoff=None, cleaned=True)
    )


def test_out_of_scope_never_returned_even_if_matched(migrated_engine: Engine) -> None:
    # An `in_scope=False` posting can't be matched in production, but the floor must hold anyway.
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    oos = _posting(migrated_engine, emp, "oos", first_seen=_NOW, in_scope=False)
    _match(migrated_engine, oos, prof, verdict="yes", score=90)
    rows = _query(migrated_engine, prof, cutoff=None, cleaned=True)
    assert "oos" not in _titles(rows)


# --- recency axis (mirrors A2's window coverage, now over matched rows) ---------------------------


def _seed_windows(engine: Engine) -> Profile:
    prof = _profile(engine)
    grid = _employer(engine, name="GridCo")
    avia = _employer(engine, vertical="aviation_software", name="AirCo")

    def matched(emp: int, title: str, **kw: object) -> None:
        pid = _posting(engine, emp, title, **kw)  # type: ignore[arg-type]
        _match(engine, pid, prof, verdict="yes", score=70)

    matched(grid, "today_fs", first_seen=_NOW, source_updated=None)
    matched(grid, "today_su", first_seen=datetime(2026, 6, 1, tzinfo=UTC), source_updated=_NOW)
    matched(
        grid,
        "week_su",
        first_seen=datetime(2026, 5, 1, tzinfo=UTC),
        source_updated=datetime(2026, 6, 17, tzinfo=UTC),
    )
    matched(
        grid, "fallback_recent", first_seen=datetime(2026, 6, 20, tzinfo=UTC), source_updated=None
    )
    matched(grid, "twoweek_only", first_seen=datetime(2026, 6, 10, tzinfo=UTC), source_updated=None)
    matched(
        grid,
        "old",
        first_seen=datetime(2026, 5, 1, tzinfo=UTC),
        source_updated=datetime(2026, 5, 2, tzinfo=UTC),
    )
    # Excluded: closed (matched but not open) + a recent matched posting in another vertical.
    closed = _posting(engine, grid, "closed", first_seen=_NOW, source_updated=_NOW, status="closed")
    _match(engine, closed, prof, verdict="yes", score=70)
    matched(avia, "other_vertical", first_seen=_NOW, source_updated=_NOW)
    return prof


def test_all_open_returns_matched_newest_first(migrated_engine: Engine) -> None:
    prof = _seed_windows(migrated_engine)
    rows = _query(migrated_engine, prof, cutoff=None)
    # Closed + other-vertical excluded; ordered by COALESCE(source_updated, first_seen) desc.
    assert set(_titles(rows)[:2]) == {"today_fs", "today_su"}  # both peak at _NOW (tie unspecified)
    # `old` (activity 2026-05-02, 50 days back) is gone: since D-109 "all open" means all open
    # *inside the age floor*. The recency axis can be switched off; the floor cannot.
    assert _titles(rows)[2:] == ["fallback_recent", "week_su", "twoweek_only"]


def test_week_window_uses_activity_date_with_fallback(migrated_engine: Engine) -> None:
    prof = _seed_windows(migrated_engine)
    rows = _query(migrated_engine, prof, cutoff=_WEEK)
    assert set(_titles(rows)) == {"today_fs", "today_su", "week_su", "fallback_recent"}


def test_two_week_window_is_a_superset_of_the_week(migrated_engine: Engine) -> None:
    prof = _seed_windows(migrated_engine)
    rows = _query(migrated_engine, prof, cutoff=_TWO_WEEKS)
    assert set(_titles(rows)) == {
        "today_fs",
        "today_su",
        "week_su",
        "fallback_recent",
        "twoweek_only",
    }


def test_new_today_uses_first_seen_only(migrated_engine: Engine) -> None:
    prof = _seed_windows(migrated_engine)
    rows = _query(migrated_engine, prof, cutoff=_MIDNIGHT, by_first_seen=True)
    # Only first_seen today — today_su (updated today, detected 06-01) excluded; = the digest.
    assert _titles(rows) == ["today_fs"]


def test_compensation_columns_are_carried_through_untouched(migrated_engine: Engine) -> None:
    """The query hands the API raw comp columns — the display judgment is `vja.comp`'s, not SQL's
    (F2 Phase A, D-087). Includes a hourly-annualized row to prove the query doesn't filter it."""
    employer_id = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    annual = _posting(
        migrated_engine,
        employer_id,
        "annual",
        first_seen=_NOW,
        comp_min=105_000,
        comp_max=131_325,
        comp_raw="$105,000 and $131,325/year",
    )
    hourly = _posting(
        migrated_engine,
        employer_id,
        "hourly",
        first_seen=_NOW,
        comp_min=103_579,
        comp_max=125_258,
        comp_raw="$49.82 to $60.22 per hour",
    )
    none_stated = _posting(migrated_engine, employer_id, "none_stated", first_seen=_NOW)
    for posting_id in (annual, hourly, none_stated):
        _match(migrated_engine, posting_id, prof, verdict="yes", score=70)

    rows = {r.title: r for r in _query(migrated_engine, prof, cutoff=None)}  # type: ignore[attr-defined]
    annual_row, hourly_row, bare_row = rows["annual"], rows["hourly"], rows["none_stated"]
    assert (annual_row.comp_min, annual_row.comp_max) == (105_000, 131_325)  # type: ignore[attr-defined]
    assert annual_row.comp_raw == "$105,000 and $131,325/year"  # type: ignore[attr-defined]
    # Not filtered here — the API's guard is what suppresses its range.
    assert hourly_row.comp_min == 103_579  # type: ignore[attr-defined]
    assert (bare_row.comp_min, bare_row.comp_raw) == (None, None)  # type: ignore[attr-defined]


# --- the age floor (D-109) ------------------------------------------------------------------
#
# A *display* floor, not a status change: the rows below stay `status='open'` throughout and are
# never touched. Age-closing them would fight the diff — the ATS still lists the job, so the next
# 4-hourly run reopens it and resets `first_seen_at`, resurfacing it as brand new every four hours
# (D-053/D-009).


def test_age_floor_hides_a_stale_posting_from_both_views(migrated_engine: Engine) -> None:
    """The complaint that motivated D-109: a board that never delists shows a 2023 role forever."""
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    for title, activity in (("fresh", _NOW), ("ghost", datetime(2023, 4, 1, tzinfo=UTC))):
        pid = _posting(migrated_engine, emp, title, first_seen=activity, source_updated=activity)
        _match(migrated_engine, pid, prof, verdict="yes", score=70)

    assert _titles(_query(migrated_engine, prof, cutoff=None)) == ["fresh"]
    assert _titles(_query(migrated_engine, prof, cutoff=None, cleaned=True)) == ["fresh"]

    # Still open in the DB — the lifespan statistics stay honest.
    with migrated_engine.connect() as conn:
        rows = conn.execute(select(postings.c.title, postings.c.status)).all()
    statuses: dict[str, str] = {str(title): str(status) for title, status in rows}
    assert statuses == {"fresh": "open", "ghost": "open"}


def test_age_floor_boundary_is_inclusive_at_exactly_the_cutoff(migrated_engine: Engine) -> None:
    """Exactly `VJA_MAX_POSTING_AGE_DAYS` old is in; one second older is out.

    Pinned because the floor is a `>=` on a coalesced date and an off-by-one here is invisible in
    production — nobody notices the day a role should have dropped.
    """
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    for title, activity in (
        ("exactly_21d", _NOW - timedelta(days=21)),
        ("21d_and_a_second", _NOW - timedelta(days=21, seconds=1)),
    ):
        pid = _posting(migrated_engine, emp, title, first_seen=activity, source_updated=activity)
        _match(migrated_engine, pid, prof, verdict="yes", score=70)

    assert _titles(_query(migrated_engine, prof, cutoff=None)) == ["exactly_21d"]


def test_age_floor_uses_the_activity_date_so_a_re_dated_role_survives(
    migrated_engine: Engine,
) -> None:
    """A board that genuinely re-dates a long-lived req keeps it alive — the correct answer, and
    the reason the floor keys on `COALESCE(source_updated_at, first_seen_at)` rather than on
    `first_seen_at`. We have tracked it for a year; the employer says it moved yesterday."""
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    pid = _posting(
        migrated_engine,
        emp,
        "long_lived_but_re_dated",
        first_seen=datetime(2025, 6, 21, tzinfo=UTC),
        source_updated=_NOW - timedelta(days=1),
    )
    _match(migrated_engine, pid, prof, verdict="yes", score=70)

    assert _titles(_query(migrated_engine, prof, cutoff=None)) == ["long_lived_but_re_dated"]


def test_age_floor_is_env_configurable(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`VJA_MAX_POSTING_AGE_DAYS` is read at call time, so a slow-moving vertical is a variable
    change rather than a deploy."""
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    pid = _posting(
        migrated_engine,
        emp,
        "thirty_days_old",
        first_seen=_NOW - timedelta(days=30),
        source_updated=_NOW - timedelta(days=30),
    )
    _match(migrated_engine, pid, prof, verdict="yes", score=70)

    assert _titles(_query(migrated_engine, prof, cutoff=None)) == []
    monkeypatch.setenv("VJA_MAX_POSTING_AGE_DAYS", "60")
    assert _titles(_query(migrated_engine, prof, cutoff=None)) == ["thirty_days_old"]
