"""The UTCDateTime column type round-trips tz-aware UTC on SQLite (fix/utc-datetime).

SQLite drops tzinfo on read; this proves our custom type re-attaches UTC and normalizes
non-UTC inputs, so application code never sees a naive datetime.
"""

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import Engine, select

from vja.db.engine import begin
from vja.db.schema import pipeline_runs


def test_timestamp_roundtrips_as_aware_utc(migrated_engine: Engine) -> None:
    aware = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
    with begin(migrated_engine) as conn:
        result = conn.execute(
            pipeline_runs.insert().values(status="ok", started_at=aware, finished_at=aware)
        )
    pk = result.inserted_primary_key
    assert pk is not None

    with migrated_engine.connect() as conn:
        started = conn.execute(
            select(pipeline_runs.c.started_at).where(pipeline_runs.c.id == pk[0])
        ).scalar_one()

    assert started.tzinfo is not None  # SQLite would normally hand back naive
    assert started.utcoffset() == timedelta(0)
    assert started == aware


def test_non_utc_aware_input_is_normalized_to_utc(migrated_engine: Engine) -> None:
    est = timezone(timedelta(hours=-5))
    local = datetime(2026, 6, 16, 7, 0, tzinfo=est)  # == 12:00Z
    with begin(migrated_engine) as conn:
        result = conn.execute(pipeline_runs.insert().values(status="ok", started_at=local))
    pk = result.inserted_primary_key
    assert pk is not None

    with migrated_engine.connect() as conn:
        started = conn.execute(
            select(pipeline_runs.c.started_at).where(pipeline_runs.c.id == pk[0])
        ).scalar_one()

    assert started == datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
