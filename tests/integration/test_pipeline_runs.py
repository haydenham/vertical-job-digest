"""Integration tests for the pipeline_runs repository (Block 3)."""

from datetime import UTC, datetime

from sqlalchemy import Engine, select

from vja.db.engine import begin
from vja.db.pipeline_runs import finish_run, start_run
from vja.db.schema import pipeline_runs
from vja.models import PipelineRunStatus


def _row(engine: Engine, run_id: int) -> dict[str, object]:
    with engine.connect() as conn:
        return dict(
            conn.execute(select(pipeline_runs).where(pipeline_runs.c.id == run_id)).mappings().one()
        )


def test_start_run_leaves_a_running_tombstone(migrated_engine: Engine) -> None:
    now = datetime(2026, 6, 16, tzinfo=UTC)
    with begin(migrated_engine) as conn:
        run_id = start_run(conn, now)

    row = _row(migrated_engine, run_id)
    assert row["status"] == PipelineRunStatus.RUNNING.value
    assert row["started_at"] is not None
    assert row["finished_at"] is None


def test_finish_run_finalizes_the_row(migrated_engine: Engine) -> None:
    start = datetime(2026, 6, 16, tzinfo=UTC)
    end = datetime(2026, 6, 16, 0, 5, tzinfo=UTC)
    with begin(migrated_engine) as conn:
        run_id = start_run(conn, start)
    with begin(migrated_engine) as conn:
        finish_run(
            conn,
            run_id,
            status=PipelineRunStatus.OK,
            employers_fetched=3,
            fetch_failures=0,
            postings_new=7,
            postings_reopened=2,
            postings_closed=1,
            errors=[],
            now=end,
        )

    row = _row(migrated_engine, run_id)
    assert row["status"] == PipelineRunStatus.OK.value
    assert row["finished_at"] is not None
    assert row["employers_fetched"] == 3
    assert row["postings_new"] == 7
    # D-103: computed all along, thrown away until now. A reopen erases its own evidence from the
    # posting row (`first_seen_at` is overwritten), so this column is the only durable record.
    assert row["postings_reopened"] == 2
    assert row["postings_closed"] == 1
    assert row["llm_cost_usd"] == 0.0
