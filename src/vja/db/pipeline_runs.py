"""pipeline_runs repository — the run's observability record (`docs/04` §7).

A row is written `running` at the start of a nightly run and finalized at the end, so a
hard crash mid-run leaves a visible `running` tombstone rather than nothing — "a failed
run is itself an alert" (CLAUDE.md). Both functions take an open `Connection`; the caller
commits each in its own transaction so the `running` row is durable before the loop begins.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.engine import Connection

from vja.db.schema import pipeline_runs
from vja.models import PipelineRunStatus


def start_run(conn: Connection, now: datetime) -> int:
    """Insert a `running` row and return its id."""
    result = conn.execute(
        pipeline_runs.insert().values(
            status=PipelineRunStatus.RUNNING.value,
            started_at=now,
        )
    )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def finish_run(
    conn: Connection,
    run_id: int,
    *,
    status: PipelineRunStatus,
    employers_fetched: int,
    fetch_failures: int,
    postings_new: int,
    postings_closed: int,
    errors: list[dict[str, Any]],
    now: datetime,
) -> None:
    """Finalize the run row with its terminal status, counts, and `finished_at`."""
    conn.execute(
        pipeline_runs.update()
        .where(pipeline_runs.c.id == run_id)
        .values(
            status=status.value,
            finished_at=now,
            employers_fetched=employers_fetched,
            fetch_failures=fetch_failures,
            postings_new=postings_new,
            postings_closed=postings_closed,
            extraction_calls=0,  # Layer-2 totals land via update_llm_metrics after the run (P5.4)
            match_calls=0,
            llm_cost_usd=0.0,
            errors=errors,
        )
    )


def update_llm_metrics(
    conn: Connection,
    run_id: int,
    *,
    extraction_calls: int,
    match_calls: int,
    llm_cost_usd: float,
) -> None:
    """Record the run's Layer-2 LLM totals (extraction + matching) after the per-vertical loop.

    `finish_run` writes 0s first (the run row is finalized before the LLM steps run); the nightly
    loop calls this once the extract/match passes are done, overwriting them with real totals.
    """
    conn.execute(
        pipeline_runs.update()
        .where(pipeline_runs.c.id == run_id)
        .values(
            extraction_calls=extraction_calls,
            match_calls=match_calls,
            llm_cost_usd=llm_cost_usd,
        )
    )
