"""Integration tests for sync_employer: fetch → diff → persist + the guard (Block 2).

Driven by a fake fetcher (no network), against a real migrated SQLite DB. These pin the
contracts that cost trust if wrong: insert/close/update arithmetic, never-delete, and
above all the no-mass-close-on-failure guard.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, select

from vja.dates import normalize_ats_date
from vja.db.engine import begin
from vja.db.schema import employers, postings
from vja.fetchers.base import FetchError
from vja.hashing import content_hash
from vja.models import AtsType, Employer, PostingStatus, RawPosting
from vja.pipeline import sync_employer


class FakeFetcher:
    """A Fetcher that returns canned postings, or raises FetchError if asked to."""

    ats_type = AtsType.GREENHOUSE

    def __init__(self, postings: list[RawPosting] | None = None, *, fail: bool = False) -> None:
        self._postings = postings or []
        self._fail = fail

    def fetch(self, employer: Employer) -> list[RawPosting]:
        if self._fail:
            raise FetchError("simulated ATS outage")
        return self._postings


def _posting(
    external_id: str,
    *,
    title: str = "Engineer",
    description: str = "Build it.",
    updated_at: str | None = None,
) -> RawPosting:
    return RawPosting(
        external_id=external_id,
        title=title,
        apply_url=f"https://example.com/{external_id}",
        location="Remote",
        updated_at=updated_at,
        raw={"id": external_id, "title": title, "content": description},
        description=description,
    )


@pytest.fixture
def employer(migrated_engine: Engine) -> Employer:
    """Insert one employer row and return its fetch-facing Employer."""
    now = datetime.now(UTC)
    with begin(migrated_engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical="grid_power_software",
                name="Example Co",
                ats_type=AtsType.GREENHOUSE.value,
                ats_slug="example",
                source="manual",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    employer_id = int(pk[0])
    return Employer(
        id=employer_id,
        vertical="grid_power_software",
        name="Example Co",
        ats_type=AtsType.GREENHOUSE,
        ats_slug="example",
    )


def _rows(engine: Engine) -> list[dict[str, object]]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(postings)).mappings().all()]


def test_first_sync_inserts_new_open_postings(migrated_engine: Engine, employer: Employer) -> None:
    now = datetime(2026, 6, 16, tzinfo=UTC)
    fetcher = FakeFetcher([_posting("a"), _posting("b")])

    result = sync_employer(migrated_engine, employer, fetcher, now=now)

    assert result.status == "ok"
    assert result.new == 2
    assert result.closed == 0
    rows = _rows(migrated_engine)
    assert len(rows) == 2
    for row in rows:
        assert row["status"] == PostingStatus.OPEN.value
        assert row["first_seen_at"] == row["last_seen_at"]
        assert row["content_hash"]


def test_resync_identical_is_idempotent(migrated_engine: Engine, employer: Employer) -> None:
    fetcher = FakeFetcher([_posting("a"), _posting("b")])
    sync_employer(migrated_engine, employer, fetcher, now=datetime(2026, 6, 16, tzinfo=UTC))

    later = datetime(2026, 6, 17, tzinfo=UTC)
    result = sync_employer(migrated_engine, employer, fetcher, now=later)

    assert result.new == 0
    assert result.closed == 0
    assert result.updated == 0
    assert result.unchanged == 2
    assert len(_rows(migrated_engine)) == 2  # no duplicates


def test_vanished_posting_is_closed_not_deleted(
    migrated_engine: Engine, employer: Employer
) -> None:
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a"), _posting("b")]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )

    # "b" disappears from the next fetch.
    result = sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a")]),
        now=datetime(2026, 6, 17, tzinfo=UTC),
    )

    assert result.closed == 1
    rows = {r["external_id"]: r for r in _rows(migrated_engine)}
    assert len(rows) == 2  # b is still present, not deleted
    assert rows["b"]["status"] == PostingStatus.CLOSED.value
    assert rows["b"]["closed_at"] is not None
    assert rows["a"]["status"] == PostingStatus.OPEN.value


def test_content_change_updates_hash_and_payload(
    migrated_engine: Engine, employer: Employer
) -> None:
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="original")]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )
    before = _rows(migrated_engine)[0]["content_hash"]

    result = sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="EDITED body")]),
        now=datetime(2026, 6, 17, tzinfo=UTC),
    )

    assert result.updated == 1
    assert result.unchanged == 0
    after = _rows(migrated_engine)[0]["content_hash"]
    assert after != before


def test_content_hash_includes_description(migrated_engine: Engine, employer: Employer) -> None:
    posting = _posting("a", title="SWE", description="unique body text")
    sync_employer(
        migrated_engine, employer, FakeFetcher([posting]), now=datetime(2026, 6, 16, tzinfo=UTC)
    )

    stored = _rows(migrated_engine)[0]["content_hash"]
    assert stored == content_hash(title="SWE", location="Remote", description="unique body text")


def _by_id(engine: Engine) -> dict[str, dict[str, object]]:
    return {str(r["external_id"]): r for r in _rows(engine)}


def test_insert_persists_normalized_source_updated_at(
    migrated_engine: Engine, employer: Employer
) -> None:
    # A Greenhouse-style ISO `updated_at` is normalized to UTC and stored on insert.
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", updated_at="2026-06-15T08:30:00-04:00")]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )
    assert _by_id(migrated_engine)["a"]["source_updated_at"] == datetime(
        2026, 6, 15, 12, 30, tzinfo=UTC
    )


def test_insert_with_no_ats_date_leaves_source_null(
    migrated_engine: Engine, employer: Employer
) -> None:
    # Workday gives no L1 date — the column stays NULL until extraction fills it.
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", updated_at=None)]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )
    assert _by_id(migrated_engine)["a"]["source_updated_at"] is None


def test_bump_backfills_null_source_updated_at(migrated_engine: Engine, employer: Employer) -> None:
    # An existing row with no date (pre-A1 / Workday corpus): a later sight whose body is
    # unchanged but now carries an `updated_at` backfills it via the bump path (the self-heal).
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="x", updated_at=None)]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )
    assert _by_id(migrated_engine)["a"]["source_updated_at"] is None

    result = sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="x", updated_at="2026-06-15T00:00:00Z")]),
        now=datetime(2026, 6, 17, tzinfo=UTC),
    )
    assert result.unchanged == 1  # body unchanged → bump path, not update
    assert _by_id(migrated_engine)["a"]["source_updated_at"] == normalize_ats_date(
        "2026-06-15T00:00:00Z"
    )


def test_content_change_refreshes_source_updated_at(
    migrated_engine: Engine, employer: Employer
) -> None:
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="orig", updated_at="2026-06-10T00:00:00Z")]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="EDITED", updated_at="2026-06-15T00:00:00Z")]),
        now=datetime(2026, 6, 17, tzinfo=UTC),
    )
    assert _by_id(migrated_engine)["a"]["source_updated_at"] == normalize_ats_date(
        "2026-06-15T00:00:00Z"
    )


def test_later_null_ats_date_does_not_clobber_existing(
    migrated_engine: Engine, employer: Employer
) -> None:
    # Once we have a good date, a subsequent fetch that omits it must not null it out.
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="orig", updated_at="2026-06-10T00:00:00Z")]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="EDITED", updated_at=None)]),
        now=datetime(2026, 6, 17, tzinfo=UTC),
    )
    assert _by_id(migrated_engine)["a"]["source_updated_at"] == normalize_ats_date(
        "2026-06-10T00:00:00Z"
    )


def _set_extracted(engine: Engine, external_id: str, when: datetime) -> None:
    """Stamp a posting as already-extracted (to assert reopen's cache-invalidation behavior)."""
    with begin(engine) as conn:
        conn.execute(
            postings.update()
            .where(postings.c.external_id == external_id)
            .values(extracted_at=when, extraction_model="haiku-test")
        )


def test_reopened_posting_is_resurrected_not_inserted(
    migrated_engine: Engine, employer: Employer
) -> None:
    # Seen, then it vanishes (closed), then it reappears — must reopen the SAME row, not insert
    # a second one (the UNIQUE(employer_id, external_id) crash this fixes).
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a")]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )
    sync_employer(  # "a" disappears → closed
        migrated_engine, employer, FakeFetcher([]), now=datetime(2026, 6, 17, tzinfo=UTC)
    )
    assert _by_id(migrated_engine)["a"]["status"] == PostingStatus.CLOSED.value

    reopen_day = datetime(2026, 6, 20, tzinfo=UTC)
    result = sync_employer(  # "a" comes back
        migrated_engine, employer, FakeFetcher([_posting("a")]), now=reopen_day
    )

    assert result.reopened == 1
    assert result.new == 0  # a reopen is not a fresh insert
    rows = _rows(migrated_engine)
    assert len(rows) == 1  # the closed row was reused, not duplicated
    row = rows[0]
    assert row["status"] == PostingStatus.OPEN.value
    assert row["closed_at"] is None
    # Surfaces as new again: first_seen_at is reset so it re-enters the digest's `new` set.
    assert row["first_seen_at"] == reopen_day
    assert row["last_seen_at"] == reopen_day


def test_reopen_with_changed_content_reextracts(
    migrated_engine: Engine, employer: Employer
) -> None:
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="original")]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )
    _set_extracted(migrated_engine, "a", datetime(2026, 6, 16, tzinfo=UTC))
    sync_employer(migrated_engine, employer, FakeFetcher([]), now=datetime(2026, 6, 17, tzinfo=UTC))

    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="EDITED while closed")]),
        now=datetime(2026, 6, 20, tzinfo=UTC),
    )

    row = _by_id(migrated_engine)["a"]
    assert row["extracted_at"] is None  # body moved → Layer-2 must re-extract
    assert row["extraction_model"] is None


def test_reopen_with_identical_content_preserves_extraction(
    migrated_engine: Engine, employer: Employer
) -> None:
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="unchanged")]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )
    extracted_when = datetime(2026, 6, 16, tzinfo=UTC)
    _set_extracted(migrated_engine, "a", extracted_when)
    sync_employer(migrated_engine, employer, FakeFetcher([]), now=datetime(2026, 6, 17, tzinfo=UTC))

    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a", description="unchanged")]),
        now=datetime(2026, 6, 20, tzinfo=UTC),
    )

    row = _by_id(migrated_engine)["a"]
    assert row["extracted_at"] == extracted_when  # identical body → cached extraction kept (D-035)
    assert row["extraction_model"] == "haiku-test"


def test_failed_fetch_closes_nothing(migrated_engine: Engine, employer: Employer) -> None:
    # Seed two open postings on a good night.
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a"), _posting("b")]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )

    # Next night the fetch fails — THE GUARD: nothing may be closed.
    result = sync_employer(
        migrated_engine, employer, FakeFetcher(fail=True), now=datetime(2026, 6, 17, tzinfo=UTC)
    )

    assert result.status == "failed"
    assert result.error
    rows = _rows(migrated_engine)
    assert len(rows) == 2
    assert all(r["status"] == PostingStatus.OPEN.value for r in rows)
    assert all(r["closed_at"] is None for r in rows)


def test_duplicate_external_ids_fail_before_any_db_mutation(
    migrated_engine: Engine, employer: Employer
) -> None:
    sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a"), _posting("b")]),
        now=datetime(2026, 6, 16, tzinfo=UTC),
    )
    before = _by_id(migrated_engine)

    result = sync_employer(
        migrated_engine,
        employer,
        FakeFetcher([_posting("a"), _posting("a", description="duplicate")]),
        now=datetime(2026, 6, 17, tzinfo=UTC),
    )

    assert result.status == "failed"
    assert result.error and "duplicate external_id" in result.error
    assert _by_id(migrated_engine) == before
