"""System-tier tests for run_pipeline (Block 3, docs/08 L3).

The whole nightly run over many employers, in-process, against a real migrated SQLite DB,
with fetchers faked via the injected `resolve_fetcher`. Pins the run-level contracts:
correct status (ok/partial/failed), per-employer failure isolation (incl. unexpected
exceptions), the run-level no-mass-close guard, idempotency, and the pipeline_runs record.
"""

import logging
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, func, select

from vja.db.engine import begin
from vja.db.schema import employers, pipeline_runs, postings
from vja.fetchers.base import FetchError
from vja.models import AtsType, Employer, PostingStatus, RawPosting
from vja.pipeline import run_pipeline

# outcome per employer: a list of postings to return, or an exception to raise
Outcome = list[RawPosting] | Exception


class FakeFetcher:
    """One fetcher whose behavior depends on the employer it's asked about."""

    ats_type = AtsType.GREENHOUSE

    def __init__(self, plan: dict[int, Outcome]) -> None:
        self._plan = plan

    def fetch(self, employer: Employer) -> list[RawPosting]:
        outcome = self._plan[employer.id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _posting(external_id: str, *, description: str = "Build it.") -> RawPosting:
    return RawPosting(
        external_id=external_id,
        title="Engineer",
        apply_url=f"https://example.com/{external_id}",
        location="Remote",
        updated_at=None,
        raw={"id": external_id, "content": description},
        description=description,
    )


def _seed_employer(engine: Engine, name: str, slug: str) -> Employer:
    now = datetime.now(UTC)
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical="grid_power_software",
                name=name,
                ats_type=AtsType.GREENHOUSE.value,
                ats_slug=slug,
                source="manual",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return Employer(
        id=int(pk[0]),
        vertical="grid_power_software",
        name=name,
        ats_type=AtsType.GREENHOUSE,
        ats_slug=slug,
    )


def _resolver(fetcher: FakeFetcher):  # type: ignore[no-untyped-def]
    return lambda _ats: fetcher


def _posting_rows(engine: Engine) -> list[dict[str, object]]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(postings)).mappings().all()]


def _run_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(pipeline_runs)).scalar_one())


def test_all_ok_run_persists_and_records_summary(migrated_engine: Engine) -> None:
    e1 = _seed_employer(migrated_engine, "Alpha", "alpha")
    e2 = _seed_employer(migrated_engine, "Beta", "beta")
    fetcher = FakeFetcher({e1.id: [_posting("a")], e2.id: [_posting("b1"), _posting("b2")]})

    summary = run_pipeline(
        migrated_engine, now=datetime(2026, 6, 16, tzinfo=UTC), resolve_fetcher=_resolver(fetcher)
    )

    assert summary.status == "ok"
    assert summary.employers_fetched == 2
    assert summary.fetch_failures == 0
    assert summary.postings_new == 3
    assert len(_posting_rows(migrated_engine)) == 3
    # exactly one pipeline_runs row, finalized
    assert _run_count(migrated_engine) == 1
    with migrated_engine.connect() as conn:
        row = conn.execute(select(pipeline_runs)).mappings().one()
    assert row["status"] == "ok"
    assert row["started_at"] is not None and row["finished_at"] is not None


def test_fetch_failure_is_partial_and_closes_nothing(migrated_engine: Engine) -> None:
    e1 = _seed_employer(migrated_engine, "Alpha", "alpha")
    e2 = _seed_employer(migrated_engine, "Beta", "beta")
    ok_day = datetime(2026, 6, 16, tzinfo=UTC)
    run_pipeline(
        migrated_engine,
        now=ok_day,
        resolve_fetcher=_resolver(FakeFetcher({e1.id: [_posting("a")], e2.id: [_posting("b")]})),
    )

    # Next night: Beta's fetch fails.
    summary = run_pipeline(
        migrated_engine,
        now=datetime(2026, 6, 17, tzinfo=UTC),
        resolve_fetcher=_resolver(
            FakeFetcher({e1.id: [_posting("a")], e2.id: FetchError("outage")})
        ),
    )

    assert summary.status == "partial"
    assert summary.fetch_failures == 1
    assert len(summary.errors) == 1
    # THE GUARD at run level: Beta's posting must NOT be closed.
    rows = {r["external_id"]: r for r in _posting_rows(migrated_engine)}
    assert rows["b"]["status"] == PostingStatus.OPEN.value
    assert rows["b"]["closed_at"] is None


def test_unexpected_exception_is_isolated_not_fatal(migrated_engine: Engine) -> None:
    e1 = _seed_employer(migrated_engine, "Alpha", "alpha")
    e2 = _seed_employer(migrated_engine, "Beta", "beta")

    summary = run_pipeline(
        migrated_engine,
        now=datetime(2026, 6, 16, tzinfo=UTC),
        resolve_fetcher=_resolver(
            FakeFetcher({e1.id: [_posting("a")], e2.id: ValueError("bug in mapping")})
        ),
    )

    assert summary.status == "partial"
    assert summary.fetch_failures == 1
    # Alpha still got persisted despite Beta blowing up.
    assert summary.postings_new == 1
    assert len(_posting_rows(migrated_engine)) == 1
    assert "ValueError" in summary.errors[0]["error"]


def test_all_failed_run_is_failed(migrated_engine: Engine) -> None:
    e1 = _seed_employer(migrated_engine, "Alpha", "alpha")
    e2 = _seed_employer(migrated_engine, "Beta", "beta")

    summary = run_pipeline(
        migrated_engine,
        now=datetime(2026, 6, 16, tzinfo=UTC),
        resolve_fetcher=_resolver(FakeFetcher({e1.id: FetchError("x"), e2.id: FetchError("y")})),
    )

    assert summary.status == "failed"
    assert summary.fetch_failures == 2
    assert _posting_rows(migrated_engine) == []


def test_rerun_is_idempotent(migrated_engine: Engine) -> None:
    e1 = _seed_employer(migrated_engine, "Alpha", "alpha")
    fetcher = FakeFetcher({e1.id: [_posting("a"), _posting("b")]})
    run_pipeline(
        migrated_engine, now=datetime(2026, 6, 16, tzinfo=UTC), resolve_fetcher=_resolver(fetcher)
    )

    summary = run_pipeline(
        migrated_engine, now=datetime(2026, 6, 17, tzinfo=UTC), resolve_fetcher=_resolver(fetcher)
    )

    assert summary.status == "ok"
    assert summary.postings_new == 0
    assert summary.postings_closed == 0
    assert len(_posting_rows(migrated_engine)) == 2
    assert _run_count(migrated_engine) == 2  # two runs recorded


def test_changed_and_failed_employer_outcomes_are_logged(
    migrated_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    e1 = _seed_employer(migrated_engine, "Alpha", "alpha")
    e2 = _seed_employer(migrated_engine, "Beta", "beta")
    # Alembic's test-only fileConfig disables loggers imported before migrations run.
    logging.getLogger("vja.pipeline").disabled = False

    with caplog.at_level(logging.INFO, logger="vja.pipeline"):
        run_pipeline(
            migrated_engine,
            now=datetime(2026, 6, 16, tzinfo=UTC),
            resolve_fetcher=_resolver(
                FakeFetcher({e1.id: [_posting("a")], e2.id: FetchError("outage")})
            ),
        )

    assert (
        "Alpha" in caplog.text
        and "fetched=1 new=1 reopened=0 updated=0 closed=0 unchanged=0" in caplog.text
    )
    assert "Beta" in caplog.text and "failed: outage" in caplog.text
