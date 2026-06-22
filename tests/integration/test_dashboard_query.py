"""Integration tests for the dashboard query (P6 B1 / D-041 / D-043) — migrated SQLite.

Pins `open_postings_with_match_quality`: the **in-scope floor** (`in_scope IS TRUE`; out-of-scope
rows never appear), the **view axis** (matched-default + relevant-only; `cleaned=True` widens to the
whole in-scope universe incl. `None`-match rows; rejected `no` never shown in either view), and the
**recency axis** (the `COALESCE(source_updated_at, first_seen_at)` activity basis with its
`first_seen_at` fallback, the first_seen-only "new today" basis, all-open) — with newest-first
ordering, vertical scoping, and open-only filtering.
"""

from datetime import UTC, datetime

from sqlalchemy import Engine

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
    assert _titles(rows)[2:] == ["fallback_recent", "week_su", "twoweek_only", "old"]


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
