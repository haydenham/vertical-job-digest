"""Integration tests for sync_employer: fetch → diff → persist + the guard (Block 2).

Driven by a fake fetcher (no network), against a real migrated SQLite DB. These pin the
contracts that cost trust if wrong: insert/close/update arithmetic, never-delete, and
above all the no-mass-close-on-failure guard.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, select

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
    external_id: str, *, title: str = "Engineer", description: str = "Build it."
) -> RawPosting:
    return RawPosting(
        external_id=external_id,
        title=title,
        apply_url=f"https://example.com/{external_id}",
        location="Remote",
        updated_at=None,
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
