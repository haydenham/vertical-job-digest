"""The unattended nightly run: fetch → diff → persist → send, in one process (P3B3).

`vja-nightly` is the single command a scheduler invokes (launchd locally — `deploy/launchd/`;
a cloud cron later, D-025). It composes the existing pieces — `run_pipeline` (Phase 2) then
`send_digest` per vertical (P3B2) — adds an aggregate status, and on a **hard failure** emails an
alert, because the builder isn't watching the run ("a failed run is itself an alert").

Portability: all logic lives here, not in the scheduler; config is env/`.env`; logs go to
stdout/stderr (the trigger decides where they land). Moving to cloud swaps the trigger, not this.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape

from sqlalchemy import Engine

from vja.db.employers import distinct_active_verticals
from vja.db.engine import get_engine
from vja.digest.render import RenderedEmail
from vja.digest.send import (
    ConfigError,
    DigestConfig,
    DigestSendResult,
    SendError,
    load_config,
    send_digest,
    send_email,
)
from vja.fetchers.base import Fetcher
from vja.fetchers.registry import get_fetcher
from vja.models import AtsType
from vja.pipeline import RunSummary, run_pipeline

logger = logging.getLogger("vja.nightly")


@dataclass(frozen=True)
class NightlyResult:
    status: str  # "ok" | "failed"
    run: RunSummary
    digests: list[DigestSendResult]
    alerted: bool


def _is_hard_failure(run: RunSummary, digests: list[DigestSendResult]) -> bool:
    """Hard failure = the whole pipeline failed, or any digest send failed.

    Partial fetch failures (some employers down, others fine) are surfaced in logs + the alert body
    but do NOT by themselves trip an alert — alert fatigue would train the builder to ignore them
    (same anti-noise logic as the empty-digest skip, D-028).
    """
    if run.status == "failed":
        return True
    return any(d.status == "failed" for d in digests)


def run_nightly(
    engine: Engine,
    *,
    now: datetime | None = None,
    config: DigestConfig | None = None,
    resolve_fetcher: Callable[[AtsType], Fetcher] = get_fetcher,
    verify: Callable[[str], bool] | None = None,
) -> NightlyResult:
    """Run the nightly loop once: pipeline across all verticals, then a digest per vertical."""
    stamp = now or datetime.now(UTC)
    cfg = config or load_config()

    run = run_pipeline(engine, vertical=None, now=stamp, resolve_fetcher=resolve_fetcher)
    logger.info(
        "pipeline run %s: status=%s employers=%d fetch_failures=%d new=%d closed=%d",
        run.run_id,
        run.status,
        run.employers_fetched,
        run.fetch_failures,
        run.postings_new,
        run.postings_closed,
    )

    digests: list[DigestSendResult] = []
    for vertical in distinct_active_verticals(engine):
        result = send_digest(engine, vertical, now=stamp, config=cfg, verify=verify)
        digests.append(result)
        logger.info(
            "digest [%s]: %s new=%d closed=%d quarantined=%d",
            result.vertical,
            result.status,
            result.new,
            result.closed,
            result.quarantined,
        )

    alerted = False
    if _is_hard_failure(run, digests):
        alerted = _send_failure_alert(cfg, run, digests)
        return NightlyResult(status="failed", run=run, digests=digests, alerted=alerted)
    return NightlyResult(status="ok", run=run, digests=digests, alerted=alerted)


def _failure_summary(run: RunSummary, digests: list[DigestSendResult]) -> str:
    lines = [
        f"pipeline: status={run.status} employers={run.employers_fetched} "
        f"fetch_failures={run.fetch_failures} new={run.postings_new} closed={run.postings_closed}"
    ]
    lines += [f"  fetch error — {e.get('name')}: {e.get('error')}" for e in run.errors]
    for d in digests:
        line = (
            f"digest [{d.vertical}]: {d.status} new={d.new} closed={d.closed} quar={d.quarantined}"
        )
        lines.append(line + (f" — {d.error}" if d.error else ""))
    return "\n".join(lines)


def _send_failure_alert(
    config: DigestConfig, run: RunSummary, digests: list[DigestSendResult]
) -> bool:
    """Email a failure alert. Returns True iff the alert sent (no-op if Resend itself is down)."""
    failed_sends = sum(1 for d in digests if d.status == "failed")
    summary = _failure_summary(run, digests)
    subject = (
        f"vja nightly FAILED — {run.fetch_failures} fetch failures, {failed_sends} send failures"
    )
    text = f"The nightly run hit a hard failure.\n\n{summary}\n"
    rendered = RenderedEmail(
        subject=subject,
        html=f"<h1>vja nightly FAILED</h1>\n<pre>{escape(text)}</pre>",
        text=text,
    )
    try:
        send_email(config, rendered)
        return True
    except SendError as exc:
        logger.error("failure-alert email could not be sent: %s", exc)
        return False


def nightly_main(argv: list[str] | None = None) -> int:
    """CLI: `vja-nightly` — run the full nightly loop once (what the scheduler invokes)."""
    argparse.ArgumentParser(
        prog="vja-nightly", description="Run the unattended nightly fetch→diff→persist→send loop."
    ).parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    try:
        config = load_config()
    except ConfigError as exc:
        logger.error("config error: %s", exc)
        return 1

    result = run_nightly(get_engine(), config=config)
    digests = "/".join(f"{d.vertical}:{d.status}" for d in result.digests) or "none"
    print(
        f"nightly: status={result.status} pipeline={result.run.status} "
        f"fetch_failures={result.run.fetch_failures} digests={digests} alerted={result.alerted}"
    )
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(nightly_main())
