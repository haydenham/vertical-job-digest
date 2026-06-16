"""Integration tests for digest assembly + the verification gate (P3B1).

Real migrated SQLite; postings/employers/digests seeded directly; verification faked
(a `Callable[[str], bool]`) so no network. Pins the window logic, the baseline rule,
vertical isolation, and that dead links are quarantined out of `new`.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine

from vja.db.engine import begin
from vja.db.schema import digests, employers, postings
from vja.digest.assembly import build_digest, last_sent_at

_PASS = lambda _url: True  # noqa: E731  (tiny test stub; a def would be noisier)


def _employer(engine: Engine, *, vertical: str = "grid_power_software", name: str = "Co") -> int:
    now = datetime.now(UTC)
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical=vertical,
                name=name,
                ats_type="greenhouse",
                ats_slug=name.lower(),
                source="manual",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _posting(
    engine: Engine,
    employer_id: int,
    external_id: str,
    *,
    first_seen: datetime,
    status: str = "open",
    closed_at: datetime | None = None,
    apply_url: str = "https://jobs.example.com/x",
) -> None:
    with begin(engine) as conn:
        conn.execute(
            postings.insert().values(
                employer_id=employer_id,
                external_id=external_id,
                content_hash=f"h-{external_id}",
                raw_payload={},
                apply_url=apply_url,
                title="Engineer",
                location="Remote",
                status=status,
                first_seen_at=first_seen,
                last_seen_at=first_seen,
                closed_at=closed_at,
            )
        )


def _digest(engine: Engine, *, vertical: str, status: str, sent_at: datetime | None) -> None:
    with begin(engine) as conn:
        conn.execute(
            digests.insert().values(
                recipient="me@example.com",
                vertical=vertical,
                status=status,
                sent_at=sent_at,
                contents={},
            )
        )


def test_baseline_first_digest_is_all_open(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    now = datetime(2026, 6, 16, tzinfo=UTC)
    _posting(migrated_engine, emp, "a", first_seen=now)
    _posting(migrated_engine, emp, "b", first_seen=now)
    _posting(migrated_engine, emp, "old", first_seen=now, status="closed", closed_at=now)

    contents = build_digest(migrated_engine, "grid_power_software", verify=_PASS)

    assert contents.since is None
    assert {p.external_id for p in contents.new} == {"a", "b"}  # the open ones
    assert contents.closed == []  # no prior state on the first digest
    assert contents.quarantined == []


def test_window_includes_only_changes_after_since(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    cutoff = datetime(2026, 6, 16, tzinfo=UTC)
    before = cutoff - timedelta(days=1)
    after = cutoff + timedelta(days=1)
    _posting(migrated_engine, emp, "old-open", first_seen=before)
    _posting(migrated_engine, emp, "new-open", first_seen=after)
    _posting(
        migrated_engine, emp, "old-closed", first_seen=before, status="closed", closed_at=before
    )
    _posting(
        migrated_engine, emp, "new-closed", first_seen=before, status="closed", closed_at=after
    )

    contents = build_digest(migrated_engine, "grid_power_software", since=cutoff, verify=_PASS)

    assert {p.external_id for p in contents.new} == {"new-open"}
    assert {p.external_id for p in contents.closed} == {"new-closed"}


def test_since_auto_resolves_from_last_sent_digest(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    cutoff = datetime(2026, 6, 16, tzinfo=UTC)
    _digest(migrated_engine, vertical="grid_power_software", status="sent", sent_at=cutoff)
    _posting(migrated_engine, emp, "old", first_seen=cutoff - timedelta(days=1))
    _posting(migrated_engine, emp, "fresh", first_seen=cutoff + timedelta(days=1))

    contents = build_digest(migrated_engine, "grid_power_software", verify=_PASS)

    assert contents.since == cutoff
    assert {p.external_id for p in contents.new} == {"fresh"}


def test_dead_links_are_quarantined(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    now = datetime(2026, 6, 16, tzinfo=UTC)
    _posting(migrated_engine, emp, "good", first_seen=now, apply_url="https://ok/1")
    _posting(migrated_engine, emp, "dead", first_seen=now, apply_url="https://dead/2")

    contents = build_digest(
        migrated_engine,
        "grid_power_software",
        verify=lambda url: url != "https://dead/2",
    )

    assert {p.external_id for p in contents.new} == {"good"}
    assert {p.external_id for p in contents.quarantined} == {"dead"}


def test_other_verticals_are_excluded(migrated_engine: Engine) -> None:
    grid = _employer(migrated_engine, vertical="grid_power_software", name="GridCo")
    avia = _employer(migrated_engine, vertical="aviation_software", name="AirCo")
    now = datetime(2026, 6, 16, tzinfo=UTC)
    _posting(migrated_engine, grid, "g1", first_seen=now)
    _posting(migrated_engine, avia, "a1", first_seen=now)

    contents = build_digest(migrated_engine, "grid_power_software", verify=_PASS)

    assert {p.external_id for p in contents.new} == {"g1"}


def test_last_sent_at_ignores_pending_and_other_verticals(migrated_engine: Engine) -> None:
    t1 = datetime(2026, 6, 10, tzinfo=UTC)
    t2 = datetime(2026, 6, 14, tzinfo=UTC)
    _digest(migrated_engine, vertical="grid_power_software", status="sent", sent_at=t1)
    _digest(migrated_engine, vertical="grid_power_software", status="sent", sent_at=t2)
    _digest(migrated_engine, vertical="grid_power_software", status="pending", sent_at=None)
    _digest(
        migrated_engine,
        vertical="aviation_software",
        status="sent",
        sent_at=datetime(2026, 6, 15, tzinfo=UTC),
    )

    assert last_sent_at(migrated_engine, "grid_power_software") == t2
    assert last_sent_at(migrated_engine, "nonexistent") is None
