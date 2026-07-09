"""Layer-3 discovery agent — finds new *employers* for a vertical (Phase 10.1 thin core).

The agent's job is NOT to find postings but to expand the universe below it (`docs/02` §4): a
weekly, deliberately-oblique web search over energy-/aviation-focused VC & PE portfolios, conference
sponsor lists, funding news, and competitors-of-X trails, producing candidate employers that land as
`proposed` + `agent_discovered` rows for human approval (D-047, `docs/04` §1). Only active
employers are fetched nightly, so proposals sit inert until a human approves them.

Two cleanly separated stages (mirrors the repo rule: LLM where structure runs out; the deterministic
fetchers stay LLM-free):

- **Stage 1 — LLM discovery.** Claude Sonnet 5 (`VJA_DISCOVER_MODEL`) with the server-side
  `web_search` + `web_fetch` tools runs an agentic research loop, then a toolless `messages.parse`
  turn structures its report into a `list[CandidateEmployer]`. The loop is **prompt-cached** (the
  growing transcript re-reads at ~0.1x) and bounded three ways: a hard **per-run dollar ceiling**
  (`VJA_DISCOVER_MAX_USD`), a **cumulative** tool budget (searches/fetches counted across resumes,
  not the per-request `max_uses` that resets), and `_MAX_CONTINUATIONS`; spend metered with the
  Block-1 `TokenUsage` at model-aware rates. The raw report is checkpointed to disk the moment
  research finishes, so a capped/interrupted run keeps what it paid for.
- **Stage 2 — deterministic validation + persist.** Each candidate is deduped against the existing
  universe, then **validated by actually fetching**: build an `Employer` from the guessed ATS/slug
  and run the matching registry fetcher (D-017 reuse). A real fetch that returns postings → a
  high-confidence `proposed` row (`verification=detected`); anything un-resolvable → `proposed` +
  `unknown` + `verification=layer2` for manual triage, the guess kept in `notes`.

Deferred to block 10.2 (out of scope here): weekly scheduling, the `vja-review` approve/reject CLI,
auto-approval, a proposal-precision eval, and discovery of non-employer `sources`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from anthropic import Anthropic
from anthropic.types import MessageParam, OutputConfigParam, ToolUnionParam
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from vja.db.employers import (
    existing_employer_names,
    insert_proposed_employer,
    normalize_employer_name,
)
from vja.db.engine import get_engine
from vja.fetchers.base import FetchError
from vja.fetchers.registry import SUPPORTED_ATS_TYPES, get_fetcher
from vja.models import AtsType, Employer, TokenUsage, Verification
from vja.verticals import load_vertical_config

logger = logging.getLogger("vja.discover")

_MODEL = os.environ.get("VJA_DISCOVER_MODEL", "claude-sonnet-5")
_EFFORT = os.environ.get("VJA_DISCOVER_EFFORT", "medium")  # bounded cost; env-overridable
# Tool budget is CUMULATIVE across the whole run (see discover_candidates). `max_uses` on the tool
# def is only a per-request bound and resets on each pause_turn resume — it is NOT the run cap.
_MAX_SEARCHES = int(os.environ.get("VJA_DISCOVER_MAX_SEARCHES", "8"))
_MAX_FETCHES = int(os.environ.get("VJA_DISCOVER_MAX_FETCHES", "8"))
_MAX_CONTINUATIONS = int(os.environ.get("VJA_DISCOVER_MAX_CONTINUATIONS", "8"))
# Hard per-run dollar kill-switch — the loop stops the turn AFTER estimated spend crosses this (so
# it can overshoot by ~one turn; caching keeps that small). The real safety net the old loop lacked.
_MAX_USD = float(os.environ.get("VJA_DISCOVER_MAX_USD", "2.0"))
_RESEARCH_MAX_TOKENS = 8_000  # per response; < the SDK's ~16k non-streaming timeout guard
_STRUCTURE_MAX_TOKENS = 4_096
_WEB_FETCH_MAX_CONTENT_TOKENS = 5_000  # cap a single fetched page so it can't bloat context

# Per-token USD rates by model prefix (standard list price — deliberately conservative so the
# kill-switch trips a hair early, not late; e.g. Sonnet 5's intro pricing of $2/$10 per MTok through
# 2026-08-31 makes real spend lower than this estimates). The meter exists so we *see* spend.
_MODEL_RATES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (3.0 / 1_000_000, 15.0 / 1_000_000),
    "claude-sonnet-4": (3.0 / 1_000_000, 15.0 / 1_000_000),
    "claude-opus-4": (5.0 / 1_000_000, 25.0 / 1_000_000),
    "claude-fable-5": (10.0 / 1_000_000, 50.0 / 1_000_000),
}
_DEFAULT_RATES = (3.0 / 1_000_000, 15.0 / 1_000_000)  # sonnet-tier fallback


def _model_rates(model: str) -> tuple[float, float]:
    """(input, output) USD-per-token for `model`, longest-prefix match; sonnet-tier fallback."""
    for key in sorted(_MODEL_RATES, key=len, reverse=True):
        if model.startswith(key):
            return _MODEL_RATES[key]
    return _DEFAULT_RATES


# Constant tool set (never varies per turn) so the cached prefix stays valid — the cumulative cap is
# enforced in the loop, not by mutating `max_uses` (which would invalidate the cache every request).
_WEB_TOOLS: list[dict[str, Any]] = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": _MAX_SEARCHES},
    {
        "type": "web_fetch_20260209",
        "name": "web_fetch",
        "max_uses": _MAX_FETCHES,
        "max_content_tokens": _WEB_FETCH_MAX_CONTENT_TOKENS,
    },
]

_RESEARCH_SYSTEM = """\
You are a sourcing analyst expanding a curated employer universe for a vertical job-intelligence
tool. Your job is to find NEW EMPLOYERS (companies that hire) for the given vertical — not postings.

Use deliberately oblique sources, not job boards:
- portfolio pages of venture/PE investors focused on this vertical,
- sponsor/exhibitor lists of the vertical's industry conferences (a sponsor list is a lead list),
- funding announcements and "competitors of X" trails.

For each promising company, use web_fetch to open its careers page and identify its
applicant-tracking system (ATS) and the company token/slug in the ATS URL. Common ATS URL shapes:
- Greenhouse: boards.greenhouse.io/{slug} or job-boards.greenhouse.io/{slug}  -> "greenhouse"
- Lever: jobs.lever.co/{slug}                                                -> ats_type "lever"
- Ashby: jobs.ashbyhq.com/{slug}                                             -> ats_type "ashby"
- Workday: {tenant}.wd{N}.myworkdayjobs.com/...  (give the full careers URL as the endpoint)
- Otherwise report your best guess or "unknown".

Do NOT propose any company already in the existing universe (below). Prefer companies genuinely
in-scope for the vertical with real early-career software/data hiring.

When done researching, write a concise report: one block per candidate with its name, careers URL,
your ATS guess, the slug (or full Workday endpoint), a category, and one line on where you found it
and why it fits."""

_STRUCTURE_SYSTEM = """\
Convert the research report into a structured list of candidate employers. Include every distinct
company the report proposes. Copy the analyst's ATS guess and slug/endpoint verbatim; use "unknown"
for ats_type when the report is unsure. Do not invent companies not present in the report."""


class CandidateEmployer(BaseModel):
    """One proposed employer as the discovery agent reports it (pre-validation).

    Lives here, not in `models.py`: it's the agent's raw output shape, not a DB entity — the same
    reason the extraction Pydantic models live in `extract.py`. The `*_guess` fields are unverified;
    Stage 2 resolves them against the real fetchers before anything is persisted.
    """

    name: str = Field(description="Company display name.")
    careers_url: str | None = Field(default=None, description="Careers page URL, or null.")
    ats_type_guess: str = Field(
        default="unknown", description="Guessed ATS slug, e.g. 'greenhouse'/'lever'/'workday'."
    )
    ats_slug_guess: str | None = Field(
        default=None, description="Company token in the ATS URL (GH/Lever/Ashby), or null."
    )
    endpoint_guess: str | None = Field(
        default=None, description="Full careers/API endpoint for Workday-style ATSs, or null."
    )
    category: str | None = Field(default=None, description="Rough category, e.g. 'IPP', 'Storage'.")
    rationale: str | None = Field(default=None, description="One line: where found + why it fits.")


class _CandidateList(BaseModel):
    """Root object for structured output (the API needs an object, not a bare list)."""

    candidates: list[CandidateEmployer] = Field(default_factory=list)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one candidate against the existing universe + the real fetchers."""

    candidate: CandidateEmployer
    outcome: str  # "fetchable" | "unresolved" | "skipped_dup"
    ats_type: AtsType = AtsType.UNKNOWN
    ats_slug: str | None = None
    endpoint: str | None = None
    verification: Verification | None = None
    posting_count: int = 0
    detail: str | None = None  # short reason, kept in the row's notes for triage


@dataclass
class DiscoverySummary:
    """What one `vja-discover` run did (observability + test assertions)."""

    vertical: str
    candidates: int = 0
    proposed_fetchable: int = 0
    proposed_unresolved: int = 0
    skipped_dup: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)
    dry_run: bool = False
    model: str = _MODEL

    @property
    def est_cost_usd(self) -> float:
        in_rate, out_rate = _model_rates(self.model)
        return self.usage.cost(in_rate, out_rate)


def _text_of(content: Any) -> str:
    """Join the text blocks of a response's content list."""
    return "\n".join(
        getattr(block, "text", "") for block in content if getattr(block, "type", None) == "text"
    ).strip()


def _count_tool_uses(content: Any) -> tuple[int, int]:
    """(web_search, web_fetch) invocations in one response — server tools emit `server_tool_use`
    blocks. Counted cumulatively across the loop so the run cap is real: per-request `max_uses`
    resets on every pause_turn resume — how the old loop ran 39 searches under a '15' cap."""
    searches = fetches = 0
    for block in content:
        if getattr(block, "type", None) == "server_tool_use":
            name = getattr(block, "name", "")
            if name == "web_search":
                searches += 1
            elif name == "web_fetch":
                fetches += 1
    return searches, fetches


def _dump_report(vertical_key: str, report: str) -> None:
    """Checkpoint the raw Stage-1 report to disk the moment research finishes, so a cost-capped or
    interrupted run keeps what it paid for (Stage-2 then persists each candidate as it goes).
    Non-fatal: a checkpoint failure must never sink the run."""
    try:
        out_dir = Path(os.environ.get("VJA_DISCOVER_REPORT_DIR", "data/discovery_reports"))
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        path = out_dir / f"{vertical_key}_{ts}.md"
        path.write_text(report, encoding="utf-8")
        logger.info("discovery report checkpointed to %s", path)
    except OSError as exc:
        logger.warning("could not checkpoint discovery report: %s", exc)


def discover_candidates(
    client: Anthropic,
    vertical_key: str,
    existing_names: set[str],
    *,
    effort: str = _EFFORT,
) -> tuple[list[CandidateEmployer], TokenUsage]:
    """Stage 1: the agentic web-research loop + a structuring turn → (candidates, metered usage)."""
    universe = "\n".join(f"- {n}" for n in sorted(existing_names)) or "(none yet)"
    user_prompt = (
        f"Vertical: {vertical_key}\n\n"
        f"Existing universe (do NOT re-propose these normalized names):\n{universe}\n\n"
        "Find new employers for this vertical, then write the per-candidate report."
    )

    in_rate, out_rate = _model_rates(_MODEL)
    usage = TokenUsage()
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]
    searches_used = fetches_used = 0
    response = None
    for _ in range(_MAX_CONTINUATIONS):
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_RESEARCH_MAX_TOKENS,
            system=_RESEARCH_SYSTEM,
            messages=cast("list[MessageParam]", messages),
            tools=cast("list[ToolUnionParam]", _WEB_TOOLS),
            thinking={"type": "adaptive"},
            output_config=cast(OutputConfigParam, {"effort": effort}),
            # Auto-cache the growing prefix (system + tools + prior turns, incl. fetched pages) so
            # each pause_turn resume re-reads it at ~0.1x instead of full input price. The old loop
            # had NO caching and re-sent the whole page-stuffed transcript uncached every turn.
            cache_control={"type": "ephemeral"},
        )
        usage = usage + TokenUsage.from_response(response.usage)
        messages.append({"role": "assistant", "content": response.content})
        s, f = _count_tool_uses(response.content)
        searches_used += s
        fetches_used += f

        spend = usage.cost(in_rate, out_rate)
        if spend >= _MAX_USD:  # hard money ceiling — the safety net the old loop lacked
            logger.warning(
                "discovery hit the $%.2f cost ceiling (VJA_DISCOVER_MAX_USD) — stopping research",
                _MAX_USD,
            )
            break
        if searches_used >= _MAX_SEARCHES or fetches_used >= _MAX_FETCHES:
            logger.info(
                "discovery hit the tool budget (searches=%d/%d fetches=%d/%d) — stopping research",
                searches_used,
                _MAX_SEARCHES,
                fetches_used,
                _MAX_FETCHES,
            )
            break
        if response.stop_reason != "pause_turn":  # server-tool loop finished → done researching
            break

    report = _text_of(response.content) if response is not None else ""
    if not report:
        logger.warning("discovery research produced no report for %s", vertical_key)
        return [], usage
    _dump_report(vertical_key, report)  # checkpoint before spending on the structuring turn

    parsed = client.messages.parse(
        model=_MODEL,
        max_tokens=_STRUCTURE_MAX_TOKENS,
        system=_STRUCTURE_SYSTEM,
        messages=[{"role": "user", "content": report}],
        output_format=_CandidateList,
    )
    usage = usage + TokenUsage.from_response(parsed.usage)
    candidates = parsed.parsed_output.candidates if parsed.parsed_output is not None else []
    return list(candidates), usage


def validate_candidate(candidate: CandidateEmployer, existing_names: set[str]) -> ValidationResult:
    """Stage 2: dedup, then prove the candidate is real by actually fetching it (D-017 reuse).

    A clean fetch that returns ≥1 posting is the bar for a high-confidence proposal. A dedup hit, an
    ATS with no Layer-1 fetcher, a fetch error, or a zero-posting board all fall to `unresolved` —
    the guess is preserved in `detail` so a human can finish the resolution.
    """
    if normalize_employer_name(candidate.name) in existing_names:
        return ValidationResult(candidate, "skipped_dup")

    guess = (candidate.ats_type_guess or "unknown").strip().lower()
    try:
        ats = AtsType(guess)
    except ValueError:
        ats = AtsType.UNKNOWN

    hint = f"agent guess: ats={guess} slug={candidate.ats_slug_guess} url={candidate.careers_url}"
    if ats not in SUPPORTED_ATS_TYPES:
        return ValidationResult(
            candidate, "unresolved", verification=Verification.LAYER2, detail=hint
        )

    probe = Employer(
        id=0,
        vertical="",
        name=candidate.name,
        ats_type=ats,
        ats_slug=candidate.ats_slug_guess,
        endpoint=candidate.endpoint_guess,
    )
    try:
        postings = get_fetcher(ats).fetch(probe)
    except (FetchError, ValueError) as exc:
        logger.info("validation fetch failed for %r: %s", candidate.name, exc)
        return ValidationResult(
            candidate, "unresolved", verification=Verification.LAYER2, detail=hint
        )

    if not postings:
        return ValidationResult(
            candidate,
            "unresolved",
            verification=Verification.LAYER2,
            detail=f"{hint} (fetch ok but 0 open postings)",
        )
    return ValidationResult(
        candidate,
        "fetchable",
        ats_type=ats,
        ats_slug=candidate.ats_slug_guess,
        endpoint=candidate.endpoint_guess,
        verification=Verification.DETECTED,
        posting_count=len(postings),
    )


def run_discovery(
    engine: Engine,
    vertical_key: str,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    client: Anthropic | None = None,
) -> DiscoverySummary:
    """Orchestrate discovery for one vertical: research → validate → persist `proposed` rows.

    `client` is injected so tests run fully offline. `dry_run` runs the LLM + validation but writes
    nothing (the loop is the metered cost either way).
    """
    load_vertical_config(vertical_key)  # validate the vertical exists before spending on the LLM
    cli = client or Anthropic()
    existing = existing_employer_names(engine, vertical_key)

    candidates, usage = discover_candidates(cli, vertical_key, existing)
    if limit is not None:
        candidates = candidates[:limit]

    summary = DiscoverySummary(
        vertical=vertical_key, candidates=len(candidates), usage=usage, dry_run=dry_run
    )
    for candidate in candidates:
        result = validate_candidate(candidate, existing)
        if result.outcome == "skipped_dup":
            summary.skipped_dup += 1
            continue

        fetchable = result.outcome == "fetchable"
        if not dry_run:
            inserted = insert_proposed_employer(
                engine,
                vertical=vertical_key,
                name=candidate.name,
                ats_type=result.ats_type,
                ats_slug=result.ats_slug,
                endpoint=result.endpoint,
                careers_url=candidate.careers_url,
                category=candidate.category,
                verification=result.verification,
                notes=_proposal_notes(candidate, result),
            )
            if inserted is None:  # lost a race to an existing (vertical, name)
                summary.skipped_dup += 1
                continue
        # count the proposal (also guard the dry-run path against re-proposing within this run)
        existing.add(normalize_employer_name(candidate.name))
        if fetchable:
            summary.proposed_fetchable += 1
        else:
            summary.proposed_unresolved += 1

    return summary


def _proposal_notes(candidate: CandidateEmployer, result: ValidationResult) -> str:
    parts = ["discovered by agent"]
    if candidate.rationale:
        parts.append(candidate.rationale)
    if result.outcome == "fetchable":
        parts.append(f"validated: {result.posting_count} open postings")
    elif result.detail:
        parts.append(result.detail)
    return " | ".join(parts)


def main(argv: list[str] | None = None) -> int:
    """CLI: `vja-discover --vertical <key> [--limit N] [--dry-run]`."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="vja-discover", description="Layer-3 employer discovery.")
    parser.add_argument("--vertical", required=True, help="vertical config key")
    parser.add_argument("--limit", type=int, default=None, help="max candidates to persist")
    parser.add_argument("--dry-run", action="store_true", help="run + meter but write nothing")
    args = parser.parse_args(argv)

    engine = get_engine()
    summary = run_discovery(engine, args.vertical, limit=args.limit, dry_run=args.dry_run)
    prefix = "[dry-run] " if summary.dry_run else ""
    print(
        f"{prefix}discover [{summary.vertical}]: candidates={summary.candidates} "
        f"proposed(fetchable)={summary.proposed_fetchable} "
        f"proposed(unresolved)={summary.proposed_unresolved} skipped_dup={summary.skipped_dup} "
        f"est_cost=${summary.est_cost_usd:.4f} "
        f"tokens(in/out/cr/cw)={summary.usage.input}/{summary.usage.output}/"
        f"{summary.usage.cache_read}/{summary.usage.cache_write}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
