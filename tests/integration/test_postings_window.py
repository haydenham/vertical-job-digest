"""Integration tests for the recency-window query (P6 A2 / D-039) — migrated SQLite.

Pins `open_postings_in_window` (D-030): the `COALESCE(source_updated_at, first_seen_at)` activity
basis with its `first_seen_at` fallback, the `first_seen_at`-only "new today" basis, the all-open
(no cutoff) case, newest-first ordering, vertical scoping, and open-only filtering.
"""

from datetime import UTC, datetime

from sqlalchemy import Engine

from vja.db.engine import begin
from vja.db.postings import open_postings_in_window
from vja.db.schema import employers, postings

_NOW = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
_MIDNIGHT = datetime(2026, 6, 21, 0, 0, tzinfo=UTC)
_WEEK = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)  # _NOW − 7d
_TWO_WEEKS = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)  # _NOW − 14d
_VERTICAL = "grid_power_software"


def _employer(engine: Engine, *, vertical: str, name: str) -> int:
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
    source_updated: datetime | None,
    status: str = "open",
) -> None:
    with begin(engine) as conn:
        conn.execute(
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
            )
        )


def _seed(engine: Engine) -> None:
    grid = _employer(engine, vertical=_VERTICAL, name="GridCo")
    avia = _employer(engine, vertical="aviation_software", name="AirCo")
    # first_seen today, no ATS date → the only true "new today".
    _posting(engine, grid, "today_fs", first_seen=_NOW, source_updated=None)
    # Old detection but the ATS *updated* it today → in every activity window, NOT new-today.
    _posting(
        engine, grid, "today_su", first_seen=datetime(2026, 6, 1, tzinfo=UTC), source_updated=_NOW
    )
    # Updated 4d ago → in the 7d + 14d windows.
    _posting(
        engine,
        grid,
        "week_su",
        first_seen=datetime(2026, 5, 1, tzinfo=UTC),
        source_updated=datetime(2026, 6, 17, tzinfo=UTC),
    )
    # No ATS date, detected yesterday → coalesce falls back to first_seen (in the 7d window).
    _posting(
        engine,
        grid,
        "fallback_recent",
        first_seen=datetime(2026, 6, 20, tzinfo=UTC),
        source_updated=None,
    )
    # No ATS date, detected 11d ago → fallback puts it in the 14d window but not the 7d one.
    _posting(
        engine,
        grid,
        "twoweek_only",
        first_seen=datetime(2026, 6, 10, tzinfo=UTC),
        source_updated=None,
    )
    # Old on both dates → only the all-open view.
    _posting(
        engine,
        grid,
        "old",
        first_seen=datetime(2026, 5, 1, tzinfo=UTC),
        source_updated=datetime(2026, 5, 2, tzinfo=UTC),
    )
    # Excluded everywhere: closed, and a recent posting in another vertical.
    _posting(engine, grid, "closed", first_seen=_NOW, source_updated=_NOW, status="closed")
    _posting(engine, avia, "other_vertical", first_seen=_NOW, source_updated=_NOW)


def _titles(rows: list) -> list[str]:  # type: ignore[type-arg]
    return [r.title for r in rows]


def test_all_open_returns_every_open_posting_newest_first(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    rows = open_postings_in_window(migrated_engine, _VERTICAL, cutoff=None)
    # Closed + other-vertical excluded; ordered by COALESCE(source_updated, first_seen) desc.
    # today_fs / today_su both peak at _NOW (order between the tie is unspecified).
    assert set(_titles(rows)[:2]) == {"today_fs", "today_su"}
    assert _titles(rows)[2:] == ["fallback_recent", "week_su", "twoweek_only", "old"]


def test_week_window_uses_activity_date_with_fallback(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    rows = open_postings_in_window(migrated_engine, _VERTICAL, cutoff=_WEEK)
    # today_su (updated today) + fallback_recent (first_seen yesterday) qualify; old/twoweek don't.
    assert set(_titles(rows)) == {"today_fs", "today_su", "week_su", "fallback_recent"}


def test_two_week_window_is_a_superset_of_the_week(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    rows = open_postings_in_window(migrated_engine, _VERTICAL, cutoff=_TWO_WEEKS)
    assert set(_titles(rows)) == {
        "today_fs",
        "today_su",
        "week_su",
        "fallback_recent",
        "twoweek_only",
    }


def test_new_today_uses_first_seen_only(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    rows = open_postings_in_window(migrated_engine, _VERTICAL, cutoff=_MIDNIGHT, by_first_seen=True)
    # Only first_seen today counts — today_su (updated today but detected 06-01) is excluded,
    # so the toggle equals the digest's `new` set (D-030).
    assert _titles(rows) == ["today_fs"]


def test_row_carries_dashboard_columns(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    rows = open_postings_in_window(migrated_engine, _VERTICAL, cutoff=None, by_first_seen=False)
    today = next(r for r in rows if r.title == "today_fs")
    assert today.company == "GridCo"
    assert today.apply_url == "https://example.com/today_fs"
    assert today.first_seen_at == _NOW
    assert today.source_updated_at is None
