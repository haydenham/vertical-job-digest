"""Layer-2 LLM matching (P5.3) — the product's actual output: a resume-match rationale.

Turns the in-scope, extracted postings that clear the two cheap gates into a written judgment
against the user's resume. Stage A (`scope.in_scope` on the title) and Stage B
(`prefilter.passes_prefilter` on the extracted level/location) drop the obvious non-matches for
free; only the survivors reach the **strong tier** here (Sonnet — D-005), which states what fits,
what does NOT fit, a verdict, and a 0-100 score (D-007: matching is reasoning, not similarity, and
the willingness to say *no* is a product requirement).

Cost discipline: the resume + instructions are the **cached prefix** (stable across every posting
in a run — the per-posting fields are the only volatile part), so the one-time backfill burst pays
the resume tokens once and reads them back for pennies. Synchronous, per-posting isolated, metered
from `usage` — same shape as extraction (`extract.py`). One `matches` row per (posting, profile,
resume_version); a re-run only matches the unmatched remainder (idempotent).
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from anthropic import Anthropic
from anthropic.types import TextBlockParam
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from vja.db.engine import begin
from vja.db.matches import MatchCandidate, postings_needing_match, save_match
from vja.db.profiles import Profile, active_profiles
from vja.models import MatchTrigger, Verdict
from vja.prefilter import PrefilterConfig, passes_prefilter
from vja.scope import in_scope
from vja.verticals import VerticalConfig

logger = logging.getLogger("vja.match")

_MODEL = "claude-sonnet-4-6"  # strong tier for the user-visible rationale (D-005); eval-gated
_BACKFILL_WINDOW_DAYS = 5  # signup catch-up cap (D-024 as amended by D-039): recent roles only
_MAX_TOKENS = 4096  # room for adaptive thinking + the structured rationale
_SONNET_IN_PER_TOKEN = 3.0 / 1_000_000  # $3 / MTok input
_SONNET_OUT_PER_TOKEN = 15.0 / 1_000_000  # $15 / MTok output
_CACHE_WRITE_MULT = 1.25  # 5-min ephemeral cache write premium
_CACHE_READ_MULT = 0.1  # cache read discount

_SYSTEM_PROMPT = """\
You are matching one early-career candidate against one job posting. You are given the candidate's
resume and the posting's structured fields, and you write an honest argument, not a sales pitch.

State, grounded only in what the resume and posting actually say:
- fits: concrete reasons this candidate fits the role (skills, domain, level). Non-empty.
- gaps: concrete reasons this candidate does NOT fit, or risks (missing skill, seniority/level
  mismatch, location/work-auth friction, domain distance). Non-empty — every real role has gaps;
  if you cannot find one you are not looking hard enough.
- verdict: strong_yes | yes | maybe | no. Saying no when warranted is required — a recommender
  that never says no is useless. Weigh level and domain fit heavily for an early-career candidate.
- score: 0-100 overall match strength, consistent with the verdict (no≈0-35, maybe≈35-60,
  yes≈60-85, strong_yes≈85-100).
- rationale: one or two sentences justifying the verdict — the line a busy job-seeker reads first.

Report only what the inputs support; never invent experience the resume doesn't state."""


class MatchResult(BaseModel):
    """The structured match judgment — maps 1:1 to the `matches` columns (`docs/04` §5, D-007)."""

    verdict: Verdict = Field(description="strong_yes | yes | maybe | no.")
    score: int = Field(ge=0, le=100, description="Overall match strength, 0-100.")
    fits: list[str] = Field(description="Concrete reasons this candidate fits. Non-empty.")
    gaps: list[str] = Field(description="Concrete reasons this candidate does not fit. Non-empty.")
    rationale: str = Field(description="One or two sentences justifying the verdict.")


@dataclass(frozen=True)
class MatchingSummary:
    vertical: str
    profiles: int
    total: int
    matched: int
    failed: int
    est_cost_usd: float


def fields_to_columns(result: MatchResult) -> dict[str, Any]:
    """Map a `MatchResult` to `matches` column values (lists → JSON text; enum → its value)."""
    return {
        "verdict": result.verdict.value,
        "score": result.score,
        "fits": json.dumps(result.fits, ensure_ascii=False),
        "gaps": json.dumps(result.gaps, ensure_ascii=False),
        "rationale": result.rationale,
    }


def _posting_text(candidate: MatchCandidate) -> str:
    """The volatile per-posting half of the prompt — the structured fields, compactly."""
    lines = [f"Title: {candidate.title or '(unknown)'}"]
    if candidate.level:
        lines.append(f"Level: {candidate.level}")
    if candidate.location:
        lines.append(f"Location: {candidate.location}")
    if candidate.remote:
        lines.append(f"Remote: {candidate.remote}")
    if candidate.work_auth:
        lines.append(f"Work authorization note: {candidate.work_auth}")
    if candidate.stack:
        lines.append(f"Stack: {', '.join(candidate.stack)}")
    comp = candidate.comp_raw or _comp_range(candidate.comp_min, candidate.comp_max)
    if comp:
        lines.append(f"Compensation: {comp}")
    return "\n".join(lines)


def _comp_range(comp_min: int | None, comp_max: int | None) -> str | None:
    if comp_min and comp_max:
        return f"${comp_min:,}-${comp_max:,}"
    return f"${comp_min:,}" if comp_min else (f"${comp_max:,}" if comp_max else None)


def _cached_system(resume_text: str, domain_vocabulary: tuple[str, ...]) -> list[TextBlockParam]:
    """The stable, cached prefix: instructions + resume + domain vocabulary (one breakpoint)."""
    vocab = ", ".join(domain_vocabulary)
    text = (
        _SYSTEM_PROMPT
        + f"\n\nDomain vocabulary (steers relevance): {vocab}\n\nCANDIDATE RESUME:\n{resume_text}"
    )
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def _call_cost(usage: Any) -> float:
    """USD cost from token usage, crediting cache reads / charging the cache-write premium."""
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cost = (
        usage.input_tokens * _SONNET_IN_PER_TOKEN
        + usage.output_tokens * _SONNET_OUT_PER_TOKEN
        + cache_write * _CACHE_WRITE_MULT * _SONNET_IN_PER_TOKEN
        + cache_read * _CACHE_READ_MULT * _SONNET_IN_PER_TOKEN
    )
    return float(cost)


def match_posting(
    client: Anthropic,
    resume_text: str,
    domain_vocabulary: tuple[str, ...],
    posting_text: str,
) -> tuple[MatchResult, float]:
    """One match call → (validated rationale, estimated USD cost from token usage)."""
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=_cached_system(resume_text, domain_vocabulary),
        messages=[{"role": "user", "content": posting_text}],
        output_format=MatchResult,
    )
    result = response.parsed_output
    if result is None:  # refusal / unparseable — surface as a failure for this posting
        raise ValueError("match returned no parsed output")
    return result, _call_cost(response.usage)


def _match_profile(
    engine: Engine,
    vertical: str,
    profile: Profile,
    *,
    config: VerticalConfig,
    client: Anthropic,
    since: datetime | None,
    trigger: MatchTrigger,
    now: datetime,
) -> tuple[int, int, float]:
    """Match one profile's Stage-A/B-surviving, unmatched candidates → (total, matched, cost).

    The shared core of nightly matching (`since=None`, `trigger=NIGHTLY`) and the signup backfill
    (`since=now−5d`, `trigger=BACKFILL`). `since` bounds the candidate set to the recency window;
    Stage A (`in_scope`) + Stage B (`passes_prefilter`) drop the obvious non-matches for free.
    Per-posting isolation: one posting's failure (API error, bad parse) is logged and skipped,
    never aborting the batch.
    """
    prefilter = PrefilterConfig(
        locations=config.prefilter_locations, levels=config.prefilter_levels
    )
    candidates = [
        c
        for c in postings_needing_match(
            engine, vertical, profile.id, profile.resume_version, since=since
        )
        if in_scope(c.title, config.scope) and passes_prefilter(c.level, c.location, prefilter)
    ]
    matched = 0
    cost = 0.0
    for candidate in candidates:
        try:
            result, call_cost = match_posting(
                client, profile.resume_text, config.domain_vocabulary, _posting_text(candidate)
            )
        except Exception as exc:  # deliberate per-posting isolation boundary (logged)
            logger.warning("match failed for posting %s: %r", candidate.posting_id, exc)
            continue
        cost += call_cost
        with begin(engine) as conn:
            save_match(
                conn,
                candidate.posting_id,
                profile.id,
                profile.resume_version,
                fields_to_columns(result),
                model=_MODEL,
                trigger=trigger.value,
                now=now,
            )
        matched += 1
    return len(candidates), matched, cost


def run_matching(
    engine: Engine,
    vertical: str,
    *,
    config: VerticalConfig,
    client: Anthropic | None = None,
    now: datetime | None = None,
) -> MatchingSummary:
    """Match every Stage-A/B-surviving, unmatched posting for `vertical` against each active resume.

    Uncapped by design (the digest's `first_seen_at` window keeps old roles out of the inbox);
    the 5-day cap is the backfill's job (`run_backfill`). `client` is injected for offline tests.
    """
    stamp = now or datetime.now(UTC)
    cli = client or Anthropic()
    profiles = active_profiles(engine, vertical)
    total = matched = 0
    cost = 0.0
    for profile in profiles:
        prof_total, prof_matched, prof_cost = _match_profile(
            engine,
            vertical,
            profile,
            config=config,
            client=cli,
            since=None,
            trigger=MatchTrigger.NIGHTLY,
            now=stamp,
        )
        total += prof_total
        matched += prof_matched
        cost += prof_cost

    return MatchingSummary(
        vertical=vertical,
        profiles=len(profiles),
        total=total,
        matched=matched,
        failed=total - matched,
        est_cost_usd=cost,
    )


def run_backfill(
    engine: Engine,
    vertical: str,
    profile: Profile,
    *,
    config: VerticalConfig,
    client: Anthropic | None = None,
    now: datetime | None = None,
) -> MatchingSummary:
    """Signup catch-up (D-024/D-039): match one new profile against the *recent* open set.

    Matches `profile` against open, extracted, unmatched postings whose ATS activity date is
    within the last `_BACKFILL_WINDOW_DAYS` (5) — so a new user's first view is timely, not a
    months-deep dump. Idempotent (a re-run only matches the unmatched remainder) and per-posting
    isolated, mirroring `run_matching`. `trigger=backfill`; `client` injected for offline tests.
    Intended caller: the future signup flow (one profile); nightly matching stays uncapped.
    """
    stamp = now or datetime.now(UTC)
    cli = client or Anthropic()
    since = stamp - timedelta(days=_BACKFILL_WINDOW_DAYS)
    total, matched, cost = _match_profile(
        engine,
        vertical,
        profile,
        config=config,
        client=cli,
        since=since,
        trigger=MatchTrigger.BACKFILL,
        now=stamp,
    )
    return MatchingSummary(
        vertical=vertical,
        profiles=1,
        total=total,
        matched=matched,
        failed=total - matched,
        est_cost_usd=cost,
    )


def match_main(argv: list[str] | None = None) -> int:
    """CLI: `vja-match [--vertical V]` — match the in-scope, extracted backlog against resumes."""
    import argparse

    from vja.db.engine import get_engine
    from vja.verticals import available_verticals, load_vertical_config

    parser = argparse.ArgumentParser(
        prog="vja-match", description="LLM-match extracted postings against active resumes."
    )
    parser.add_argument("--vertical", default=None, help="limit to one vertical (default: all)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv()  # load `.env` (ANTHROPIC_API_KEY) before constructing the Anthropic client
    engine = get_engine()
    verticals = [args.vertical] if args.vertical else available_verticals()
    for vertical in verticals:
        cfg = load_vertical_config(vertical)
        summary = run_matching(engine, vertical, config=cfg)
        print(
            f"[{summary.vertical}] matched {summary.matched}/{summary.total} across "
            f"{summary.profiles} profile(s) (failed {summary.failed}) "
            f"est_cost=${summary.est_cost_usd:.4f}"
        )
    return 0


def backfill_main(argv: list[str] | None = None) -> int:
    """CLI: `vja-backfill --vertical V [--email X]` — signup catch-up over the recent open set.

    Runs the 5-day-capped backfill (`trigger=backfill`) for each active profile in the vertical
    (optionally just `--email`). The standalone manual entry point until a real signup flow calls
    `run_backfill` directly (multi-user cutover, D-025).
    """
    import argparse

    from vja.db.engine import get_engine
    from vja.verticals import load_vertical_config

    parser = argparse.ArgumentParser(
        prog="vja-backfill",
        description="Signup backfill: match recent open postings against active resumes.",
    )
    parser.add_argument("--vertical", required=True, help="the vertical to backfill")
    parser.add_argument("--email", default=None, help="limit to one profile by user email")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv()  # load `.env` (ANTHROPIC_API_KEY) before constructing the Anthropic client
    engine = get_engine()
    cfg = load_vertical_config(args.vertical)
    profiles = [
        p
        for p in active_profiles(engine, args.vertical)
        if args.email is None or p.user_email == args.email
    ]
    if not profiles:
        print(f"no active profiles for vertical {args.vertical!r}", file=sys.stderr)
        return 0
    for profile in profiles:
        summary = run_backfill(engine, args.vertical, profile, config=cfg)
        print(
            f"[{summary.vertical}→{profile.user_email}] backfilled "
            f"{summary.matched}/{summary.total} (failed {summary.failed}) "
            f"est_cost=${summary.est_cost_usd:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(match_main())
