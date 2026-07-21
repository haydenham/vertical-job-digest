"""The unattended nightly run: fetch → diff → extract → match → send, one process (P3B3/P5.4).

`vja-nightly` is the single command a scheduler invokes (launchd locally — `deploy/launchd/`;
a cloud cron later, D-025). It composes the existing pieces — `run_pipeline` (Phase 2), then the
Layer-2 LLM passes per vertical (`run_extraction` + `run_matching`, P5.2/P5.3), then `send_digest`
per (vertical, profile) (P3B2 + D-027) — adds an aggregate status, records the run's LLM totals,
and on a **hard failure** emails an alert, because the builder isn't watching the run ("a failed
run is itself an alert").

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

from vja.db.engine import begin, get_engine
from vja.db.pipeline_runs import update_llm_metrics
from vja.db.profiles import active_profiles
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
from vja.extract import run_extraction
from vja.fetchers.base import Fetcher
from vja.fetchers.registry import get_fetcher
from vja.llm import LiteLLMClient, StructuredLLM, sum_catalog_costs
from vja.match import run_matching
from vja.models import AtsType, TokenUsage
from vja.pipeline import RunSummary, run_pipeline
from vja.prefilter import PrefilterConfig
from vja.verticals import available_verticals, load_vertical_config

logger = logging.getLogger("vja.nightly")


@dataclass(frozen=True)
class Layer2Summary:
    """The Layer-2 LLM totals for one vertical (extraction + matching)."""

    extracted: int
    matched: int
    est_cost_usd: float | None
    extract_usage: TokenUsage = TokenUsage()
    match_usage: TokenUsage = TokenUsage()


# The per-vertical Layer-2 pass, injected so tests run fully offline (mirrors `resolve_fetcher`).
Layer2Runner = Callable[..., Layer2Summary]


def _default_layer2(
    engine: Engine, vertical: str, *, client: StructuredLLM | None, now: datetime
) -> Layer2Summary:
    """Extract then match one vertical against its config; one client shared across both passes."""
    cli = client or LiteLLMClient()
    vcfg = load_vertical_config(vertical)
    ext = run_extraction(
        engine,
        vertical,
        scope=vcfg.scope,
        prefilter=PrefilterConfig(locations=vcfg.prefilter_locations, levels=vcfg.prefilter_levels),
        client=cli,
        now=now,
    )
    mat = run_matching(engine, vertical, config=vcfg, client=cli, now=now)
    return Layer2Summary(
        extracted=ext.extracted,
        matched=mat.matched,
        est_cost_usd=sum_catalog_costs(ext.est_cost_usd, mat.est_cost_usd),
        extract_usage=ext.usage,
        match_usage=mat.usage,
    )


@dataclass(frozen=True)
class NightlyResult:
    status: str  # "ok" | "failed"
    run: RunSummary
    digests: list[DigestSendResult]
    alerted: bool
    extraction_calls: int = 0
    match_calls: int = 0
    llm_cost_usd: float | None = 0.0


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
    client: StructuredLLM | None = None,
    run_layer2: Layer2Runner = _default_layer2,
) -> NightlyResult:
    """Run the nightly loop once: pipeline → (extract → match → send per profile) per vertical."""
    stamp = now or datetime.now(UTC)
    cfg = config or load_config()

    run = run_pipeline(engine, vertical=None, now=stamp, resolve_fetcher=resolve_fetcher)
    logger.info(
        "pipeline run %s: status=%s employers=%d fetch_failures=%d new=%d reopened=%d closed=%d",
        run.run_id,
        run.status,
        run.employers_fetched,
        run.fetch_failures,
        run.postings_new,
        run.postings_reopened,
        run.postings_closed,
    )

    digests: list[DigestSendResult] = []
    extraction_calls = match_calls = 0
    llm_cost: float | None = 0.0
    usage = TokenUsage()
    # Layer 2 + digests are config-driven (a "vertical is config"): each config-backed vertical
    # gets its LLM passes, then one digest per active profile (D-027).
    for vertical in available_verticals():
        try:
            l2 = run_layer2(engine, vertical, client=client, now=stamp)
        except Exception:  # per-vertical isolation: one vertical's Layer-2 error can't kill the run
            logger.exception("layer-2 pass failed for vertical %s", vertical)
            l2 = Layer2Summary(extracted=0, matched=0, est_cost_usd=0.0)
        extraction_calls += l2.extracted
        match_calls += l2.matched
        llm_cost = sum_catalog_costs(llm_cost, l2.est_cost_usd)
        usage = usage + l2.extract_usage + l2.match_usage
        # The real per-stage token meter (D-069) — replaces the old $0.01/item proxy. Cache hit % is
        # the matching prompt-cache signal: near-0 means the resume prefix isn't clearing the
        # 2048-token floor; the extraction line shows whether description input is uncacheable.
        estimated_cost = f"${l2.est_cost_usd:.4f}" if l2.est_cost_usd is not None else "unavailable"
        logger.info(
            "layer-2 [%s]: extracted=%d (in=%d out=%d) matched=%d (in=%d out=%d "
            "cache_read=%d cache_write=%d hit=%.0f%%) est_cost=%s",
            vertical,
            l2.extracted,
            l2.extract_usage.input,
            l2.extract_usage.output,
            l2.matched,
            l2.match_usage.input,
            l2.match_usage.output,
            l2.match_usage.cache_read,
            l2.match_usage.cache_write,
            l2.match_usage.cache_hit_rate * 100,
            estimated_cost,
        )

        for profile in active_profiles(engine, vertical):
            result = send_digest(engine, vertical, profile, now=stamp, config=cfg, verify=verify)
            digests.append(result)
            logger.info(
                "digest [%s→%s]: %s new=%d closed=%d quarantined=%d",
                result.vertical,
                result.recipient,
                result.status,
                result.new,
                result.closed,
                result.quarantined,
            )

    with begin(engine) as conn:
        update_llm_metrics(
            conn,
            run.run_id,
            extraction_calls=extraction_calls,
            match_calls=match_calls,
            llm_cost_usd=llm_cost,
            usage=usage,
        )

    alerted = False
    status = "failed" if _is_hard_failure(run, digests) else "ok"
    if status == "failed":
        alerted = _send_failure_alert(cfg, run, digests)
    return NightlyResult(
        status=status,
        run=run,
        digests=digests,
        alerted=alerted,
        extraction_calls=extraction_calls,
        match_calls=match_calls,
        llm_cost_usd=llm_cost,
    )


def _failure_summary(run: RunSummary, digests: list[DigestSendResult]) -> str:
    lines = [
        f"pipeline: status={run.status} employers={run.employers_fetched} "
        f"fetch_failures={run.fetch_failures} new={run.postings_new} "
        f"reopened={run.postings_reopened} closed={run.postings_closed}"
    ]
    lines += [f"  fetch error — {e.get('name')}: {e.get('error')}" for e in run.errors]
    for d in digests:
        line = (
            f"digest [{d.vertical}→{d.recipient}]: {d.status} "
            f"new={d.new} closed={d.closed} quar={d.quarantined}"
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
    digests = "/".join(f"{d.vertical}→{d.recipient}:{d.status}" for d in result.digests) or "none"
    estimated_cost = (
        f"${result.llm_cost_usd:.4f}" if result.llm_cost_usd is not None else "unavailable"
    )
    print(
        f"nightly: status={result.status} pipeline={result.run.status} "
        f"fetch_failures={result.run.fetch_failures} "
        f"extracted={result.extraction_calls} matched={result.match_calls} "
        f"llm_cost={estimated_cost} digests={digests} alerted={result.alerted}"
    )
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(nightly_main())
