"""Layer-2 LLM matching (P5.3) — the product's actual output: a resume-match rationale.

Turns the in-scope, extracted postings that clear the two cheap gates into a written judgment
against the user's resume. Stage A (`scope.in_scope` on the title) and Stage B
(`prefilter.passes_prefilter` on the extracted level/location) drop the obvious non-matches for
free; only the survivors reach the configured rationale model, which states what fits,
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
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine

from vja.db.engine import begin
from vja.db.matches import (
    MatchCandidate,
    count_matches_since,
    postings_needing_match,
    save_match,
)
from vja.db.profiles import Profile, active_profiles, mark_backfill_completed
from vja.llm import LiteLLMClient, StructuredLLM, StructuredResult, sum_catalog_costs
from vja.models import MatchTrigger, TokenUsage, Verdict
from vja.prefilter import PrefilterConfig, passes_prefilter
from vja.scope import in_scope
from vja.verticals import VerticalConfig

logger = logging.getLogger("vja.match")

_DEFAULT_MODEL = "openai/gpt-5.6-luna"
_BACKFILL_WINDOW_DAYS = 5  # signup catch-up cap (D-024 as amended by D-039): recent roles only
_MAX_TOKENS = 4096  # room for reasoning + the structured rationale
# Matching is a bounded, schema-constrained judgment task. The D-090 comparison found Luna `low`
# preserved trust while beating both Luna `medium` and Sonnet `medium` on latency and cost.
_DEFAULT_MATCH_EFFORT = "low"
# Posting-body budget for the match prompt (D-111). Bodies average ~3 KB, so this clips only the
# long ones — and clips their tail, which is boilerplate. ~1,000 volatile (uncached) input tokens
# at the ceiling; the cached resume prefix is unaffected.
_DEFAULT_DESCRIPTION_CHARS = 4000


def _match_effort() -> str:
    """Configured reasoning effort, read at call time (mirrors the backfill knobs)."""
    return os.environ.get("VJA_MATCH_EFFORT") or _DEFAULT_MATCH_EFFORT


# Cost/abuse guards (D-057) — the signup backfill is the first user action that spends LLM tokens.
# Both are env-tunable (read at call time so tests can set them) with conservative defaults.
_DEFAULT_BACKFILL_MAX_POSTINGS = 100  # hard cap on candidates matched per signup
# Daily *backfill* spend ceiling (D-101 narrowed it from all-triggers). The default stays low for a
# dev machine; prod sets VJA_DAILY_LLM_BUDGET_USD explicitly in deploy/gcp/ship.sh, where the value
# is greppable next to the other prod knobs.
_DEFAULT_DAILY_LLM_BUDGET_USD = 5.0
# Spend proxy per match (no per-match ledger; see count_matches_since). Deliberately ~5x the
# measured per-match cost — a guard should overestimate.
_NOMINAL_MATCH_USD = 0.01


def _match_model() -> str:
    """LiteLLM model route, read at call time so deployments can switch without code changes."""
    return os.environ.get("VJA_MATCH_MODEL") or _DEFAULT_MODEL


_SYSTEM_PROMPT = """\
You are advising one early-career candidate on one job posting. You are given their resume and the
posting, and you write an honest assessment plus advice they can act on before they apply.

Write to the candidate directly, as "you" and "your", in every field. Never describe them in the
third person ("the candidate", "they") — this text is read by the person it is about.

State, grounded only in what the resume and posting actually say:
- fits: AT MOST 3 concrete reasons you fit (skills, domain, level). Non-empty. Choose the strongest
  and stop; do not pad to three.
- gaps: AT MOST 3 concrete reasons you do not fit, or real risks (missing skill, seniority/level
  mismatch, domain distance). Non-empty — every real role has gaps; if you cannot find one you are
  not looking hard enough.
- verdict: strong_yes | yes | maybe | no. Saying no when warranted is required — a recommender
  that never says no is useless. Weigh level and domain fit heavily for an early-career candidate.
- score: 0-100 overall match strength, consistent with the verdict (no≈0-35, maybe≈35-60,
  yes≈60-85, strong_yes≈85-100).
- rationale: one or two sentences naming what DOMINATED the judgment — the consideration that set
  the score. It is not a summary of the lists above, which are displayed right beside it. Do not
  restate the verdict or score in words ("overall this is a plausible match", "so this is a maybe");
  they are already shown as a label. Name the deciding factor and stop.
- resume_actions: AT MOST 3 specific edits to your resume for THIS application. Every action must
  point at something already on your resume: experience worth leading with, real work buried under
  "projects" that belongs higher, or wording to change because the posting says the same thing
  differently. Where the posting has its own term for something you have done, quote that term.
- application_notes: AT MOST 2 notes on what the application itself should address — how to frame a
  real gap, what a cover letter or screening answer should confront rather than leave for them to
  find. This is where a gap you cannot fix by editing belongs.

Never tell the candidate to add a skill, tool, or experience their resume does not already
evidence. That is advice to lie, and it is the worst thing this product can do. The honest response
to a real gap is how to ADDRESS it, never how to hide it.

Both advice lists may be empty, and empty is the right answer more often than padding. When the
mismatch is fundamental — a different engineering discipline, a hard eligibility conflict — say so
in the rationale and return empty lists. "Nothing you change about your resume makes this fit" is a
complete, useful answer; an invented bridge to an impossible role is not.

Do not spend a fits or gaps bullet on facts that are true of you for every posting — your
graduation date, where you live relative to the role, or that your level suits an early-career job.
Those repeat on every role and say nothing about this one. Raise such a fact only where it is
genuinely decisive here, such as a hard eligibility conflict.

Calibrate experience against the role's stated level. For new-grad and early-career roles,
relevant internships, coursework, and substantial projects are valid evidence; do not cap an
otherwise excellent match below strong_yes merely because you lack production depth.
For a US role, an unstated willingness to relocate or work onsite is neutral: you may mention the
location logistics, but never lower the verdict or score for that uncertainty. Only an explicit
geographic or work-authorization incompatibility counts negatively. Preserve maybe or no for
mid/senior level mismatches and hard eligibility conflicts.

When the posting includes a description, it is the source for the posting's own vocabulary: prefer
its exact words over your paraphrase when advising a wording change.

Report only what the inputs support; never invent experience the resume doesn't state."""


class MatchResult(BaseModel):
    """The structured match judgment — maps 1:1 to the `matches` columns (`docs/04` §5, D-007)."""

    verdict: Verdict = Field(description="strong_yes | yes | maybe | no.")
    score: int = Field(ge=0, le=100, description="Overall match strength, 0-100.")
    fits: list[str] = Field(description="At most 3 concrete reasons you fit. Non-empty.")
    gaps: list[str] = Field(description="At most 3 concrete reasons you do not fit. Non-empty.")
    rationale: str = Field(description="One or two sentences naming what decided the verdict.")
    # The advice fields (D-111). Both default to empty rather than being required: an impossible
    # match has no honest advice, and the prompt says so explicitly — a model that returns nothing
    # here is obeying, not failing. `fits`/`gaps` stay required for the opposite reason (D-007).
    resume_actions: list[str] = Field(
        default_factory=list,
        description=(
            "At most 3 edits to your resume for this application, each grounded in something the "
            "resume already contains. Empty when there is nothing honest to change."
        ),
    )
    application_notes: list[str] = Field(
        default_factory=list,
        description=(
            "At most 2 notes on what the application should address about a gap you cannot fix by "
            "editing. Empty when there is nothing useful to say."
        ),
    )

    @field_validator("score", mode="before")
    @classmethod
    def normalize_score_boundary(cls, value: object) -> object:
        """Keep one numeric boundary miss from discarding an otherwise valid paid result.

        Anthropic's schema transform preserves ``integer`` but moves unsupported JSON-Schema
        minimum/maximum constraints into descriptive text. The model can therefore emit an
        integer outside 0–100 even though our final domain contract is strict. Normalize only
        real integers; wrong types and every other malformed field still fail validation.
        """
        if type(value) is not int:
            return value
        normalized = min(100, max(0, value))
        if normalized != value:
            logger.warning("normalized match score %d → %d", value, normalized)
        return normalized


@dataclass(frozen=True)
class MatchingSummary:
    vertical: str
    profiles: int
    total: int
    matched: int
    failed: int
    est_cost_usd: float | None
    usage: TokenUsage = TokenUsage()


class BackfillBudgetExceeded(RuntimeError):
    """The estimated LLM spend for today is already over the daily ceiling, so a new signup
    backfill is refused (D-057). The API maps this to a 429."""


def _backfill_max_postings() -> int:
    """The per-signup candidate cap (`VJA_BACKFILL_MAX_POSTINGS`), read at call time."""
    raw = os.environ.get("VJA_BACKFILL_MAX_POSTINGS")
    return int(raw) if raw else _DEFAULT_BACKFILL_MAX_POSTINGS


def _pipeline_max_matches() -> int | None:
    """Per-profile cap on one *pipeline* run's matching (`VJA_PIPELINE_MAX_MATCHES`), or None.

    D-103's cost guard for the 4-hourly cadence. Total spend is roughly flat under the split —
    the same postings cost the same, just discovered sooner — so this is not a budget but a
    runaway bound: at six runs a day, a mistake that inflates the candidate set (a bad extraction
    invalidation, a large employer add) gets six chances a day instead of one. Unset by default,
    which is today's uncapped behavior (D-039).

    Deliberately *not* the D-057 daily ceiling: that one refuses work outright and is keyed to
    signups, so reusing it here would let a big pipeline run 429 a new user at onboarding —
    exactly the coupling D-101 removed. Overflow here is simply deferred: uncapped candidates stay
    in `postings_needing_match` and are picked up by the next run, 4 hours later.
    """
    raw = os.environ.get("VJA_PIPELINE_MAX_MATCHES")
    return int(raw) if raw else None


def _daily_budget_usd() -> float:
    """The global daily LLM-spend ceiling (`VJA_DAILY_LLM_BUDGET_USD`), read at call time."""
    raw = os.environ.get("VJA_DAILY_LLM_BUDGET_USD")
    return float(raw) if raw else _DEFAULT_DAILY_LLM_BUDGET_USD


def estimate_daily_backfill_spend(engine: Engine, now: datetime) -> float:
    """Estimated *signup-backfill* LLM spend so far today (UTC) = backfill-trigger matches created
    since midnight × nominal per-match cost. A proxy, not an invoice — enough to backstop signup
    spend without a per-match ledger.

    Nightly matches are deliberately excluded (D-101). The ceiling only ever gated the signup path
    (its one caller is `POST /api/profiles`), while the nightly is uncapped by design (D-039), so
    counting the nightly meant a large run could refuse new users for spend the guard could not
    prevent: on 2026-07-25 the nightly alone reached $4.55 of the then-$5 ceiling."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    count = count_matches_since(engine, midnight, trigger=MatchTrigger.BACKFILL)
    return count * _NOMINAL_MATCH_USD


def check_backfill_budget(engine: Engine, now: datetime | None = None) -> None:
    """Raise `BackfillBudgetExceeded` if today's estimated backfill spend is already over the
    ceiling.

    Called *before* a signup backfill is scheduled, so the work never starts once the day's budget
    is spent — the global cost guard on top of the per-backfill cap (D-057, D-101)."""
    stamp = now or datetime.now(UTC)
    spend = estimate_daily_backfill_spend(engine, stamp)
    budget = _daily_budget_usd()
    if spend >= budget:
        raise BackfillBudgetExceeded(
            f"daily LLM budget reached (est ${spend:.2f} ≥ ${budget:.2f}); try again tomorrow"
        )


def fields_to_columns(result: MatchResult) -> dict[str, Any]:
    """Map a `MatchResult` to `matches` column values (lists → JSON text; enum → its value).

    The advice lists are stored as JSON text like `fits`/`gaps`, and an **empty list is stored as
    `"[]"`, not NULL** — the two mean different things on the read side. `"[]"` is this model
    saying there is no honest advice for this role (D-111); NULL is a row matched before the
    fields existed. Both render nothing, but only one of them is a judgment.
    """
    return {
        "verdict": result.verdict.value,
        "score": result.score,
        "fits": json.dumps(result.fits, ensure_ascii=False),
        "gaps": json.dumps(result.gaps, ensure_ascii=False),
        "rationale": result.rationale,
        "resume_actions": json.dumps(result.resume_actions, ensure_ascii=False),
        "application_notes": json.dumps(result.application_notes, ensure_ascii=False),
    }


def _max_description_chars() -> int:
    """Character budget for the posting body in the match prompt (`VJA_MATCH_DESCRIPTION_CHARS`).

    Read at call time so tightening it after a cost measurement is a config change, not a deploy
    (the `VJA_MAX_POSTING_AGE_DAYS` pattern, D-109).
    """
    raw = os.environ.get("VJA_MATCH_DESCRIPTION_CHARS")
    return int(raw) if raw else _DEFAULT_DESCRIPTION_CHARS


def _posting_text(candidate: MatchCandidate) -> str:
    """The volatile per-posting half of the prompt — the structured fields, compactly.

    The body is included last and **head-truncated** (D-111): advice of the form "the posting calls
    this a data pipeline and your resume says ETL" is impossible without the posting's own words,
    and the extracted `stack` list is too thin to carry them. Head, not tail, because a posting
    front-loads its responsibilities and back-loads its boilerplate (EEO, benefits, legal) — so the
    truncation drops the part that was never worth tokens. Rows with no stored body (D-095 fills
    forward, never backfills) simply omit it and still match.
    """
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
    if candidate.description:
        lines.append(f"\nDescription:\n{candidate.description[: _max_description_chars()]}")
    return "\n".join(lines)


def _comp_range(comp_min: int | None, comp_max: int | None) -> str | None:
    if comp_min and comp_max:
        return f"${comp_min:,}-${comp_max:,}"
    return f"${comp_min:,}" if comp_min else (f"${comp_max:,}" if comp_max else None)


def _cached_system(resume_text: str, domain_vocabulary: tuple[str, ...]) -> str:
    """The stable, cached prefix: instructions + resume + domain vocabulary (one breakpoint)."""
    vocab = ", ".join(domain_vocabulary)
    text = (
        _SYSTEM_PROMPT
        + f"\n\nDomain vocabulary (steers relevance): {vocab}\n\nCANDIDATE RESUME:\n{resume_text}"
    )
    return text


def match_posting(
    client: StructuredLLM,
    resume_text: str,
    domain_vocabulary: tuple[str, ...],
    posting_text: str,
) -> StructuredResult[MatchResult]:
    """One match call → validated judgment plus catalog-priced, normalized metadata."""
    return client.parse(
        model=_match_model(),
        max_tokens=_MAX_TOKENS,
        system=_cached_system(resume_text, domain_vocabulary),
        user=posting_text,
        response_model=MatchResult,
        reasoning_effort=_match_effort(),
        cache_system=True,
    )


def _match_profile(
    engine: Engine,
    vertical: str,
    profile: Profile,
    *,
    config: VerticalConfig,
    client: StructuredLLM,
    since: datetime | None,
    trigger: MatchTrigger,
    now: datetime,
    max_postings: int | None = None,
) -> tuple[int, int, TokenUsage, float | None]:
    """Match one profile's Stage-A/B-surviving, unmatched candidates → (total, matched, usage).

    The shared core of nightly matching (`since=None`, `trigger=NIGHTLY`) and the signup backfill
    (`since=now−5d`, `trigger=BACKFILL`). `since` bounds the candidate set to the recency window;
    `now` additionally applies the age floor, which drops postings we could not display even if
    we matched them. Stage A (`in_scope`) + Stage B (`passes_prefilter`) drop the rest for free.
    `max_postings` caps the surviving set (the backfill cost guard, D-057) — `None` for the
    uncapped nightly path. Per-posting isolation: one posting's failure (API error, bad parse) is
    logged and skipped, never aborting the batch.
    """
    prefilter = PrefilterConfig(
        locations=config.prefilter_locations, levels=config.prefilter_levels
    )
    candidates = [
        c
        for c in postings_needing_match(
            engine, vertical, profile.id, profile.resume_version, now=now, since=since
        )
        if in_scope(c.title, config.scope) and passes_prefilter(c.level, c.location, prefilter)
    ]
    if max_postings is not None and len(candidates) > max_postings:
        logger.warning(
            "match cap hit [%s/%s/profile %d]: %d candidates truncated to %d (freshest first); "
            "the remainder is deferred to the next run, not dropped",
            vertical,
            trigger.value,
            profile.id,
            len(candidates),
            max_postings,
        )
        candidates = candidates[:max_postings]
    matched = 0
    usage = TokenUsage()
    cost_usd: float | None = 0.0
    for candidate in candidates:
        try:
            call = match_posting(
                client, profile.resume_text, config.domain_vocabulary, _posting_text(candidate)
            )
        except Exception as exc:  # deliberate per-posting isolation boundary (logged)
            logger.warning("match failed for posting %s: %r", candidate.posting_id, exc)
            continue
        usage = usage + call.usage
        cost_usd = sum_catalog_costs(cost_usd, call.cost_usd)
        with begin(engine) as conn:
            save_match(
                conn,
                candidate.posting_id,
                profile.id,
                profile.resume_version,
                fields_to_columns(call.value),
                model=call.model,
                trigger=trigger.value,
                now=now,
            )
        matched += 1
    return len(candidates), matched, usage, cost_usd


def run_matching(
    engine: Engine,
    vertical: str,
    *,
    config: VerticalConfig,
    client: StructuredLLM | None = None,
    now: datetime | None = None,
) -> MatchingSummary:
    """Match every Stage-A/B-surviving, unmatched posting for `vertical` against each active resume.

    Date-uncapped by design (the digest's `first_seen_at` window keeps old roles out of the inbox);
    the 5-day cap is the backfill's job (`run_backfill`). `VJA_PIPELINE_MAX_MATCHES` optionally
    bounds the count *per profile per vertical per run* (D-103 runaway guard, unset by default);
    anything over the cap is not dropped, just deferred to the next run. `client` is injected for
    offline tests.
    """
    stamp = now or datetime.now(UTC)
    cli = client or LiteLLMClient()
    profiles = active_profiles(engine, vertical)
    max_postings = _pipeline_max_matches()
    total = matched = 0
    usage = TokenUsage()
    cost_usd: float | None = 0.0
    for profile in profiles:
        prof_total, prof_matched, prof_usage, prof_cost = _match_profile(
            engine,
            vertical,
            profile,
            config=config,
            client=cli,
            since=None,
            trigger=MatchTrigger.NIGHTLY,
            now=stamp,
            max_postings=max_postings,
        )
        total += prof_total
        matched += prof_matched
        usage = usage + prof_usage
        cost_usd = sum_catalog_costs(cost_usd, prof_cost)

    return MatchingSummary(
        vertical=vertical,
        profiles=len(profiles),
        total=total,
        matched=matched,
        failed=total - matched,
        est_cost_usd=cost_usd,
        usage=usage,
    )


def run_backfill(
    engine: Engine,
    vertical: str,
    profile: Profile,
    *,
    config: VerticalConfig,
    client: StructuredLLM | None = None,
    now: datetime | None = None,
) -> MatchingSummary:
    """Signup catch-up (D-024/D-039): match one new profile against the *recent* open set.

    Matches `profile` against open, extracted, unmatched postings whose ATS activity date is
    within the last `_BACKFILL_WINDOW_DAYS` (5) — so a new user's first view is timely, not a
    months-deep dump. The surviving set is capped at `VJA_BACKFILL_MAX_POSTINGS` (D-057) so one
    signup can't run away on cost. Idempotent (a re-run only matches the unmatched remainder) and
    per-posting isolated, mirroring `run_matching`. `trigger=backfill`; `client` injected for
    offline tests. Intended caller: the signup upload flow (one profile); nightly stays uncapped.
    """
    stamp = now or datetime.now(UTC)
    cli = client or LiteLLMClient()
    since = stamp - timedelta(days=_BACKFILL_WINDOW_DAYS)
    try:
        total, matched, usage, cost_usd = _match_profile(
            engine,
            vertical,
            profile,
            config=config,
            client=cli,
            since=since,
            trigger=MatchTrigger.BACKFILL,
            now=stamp,
            max_postings=_backfill_max_postings(),
        )
    finally:
        # The completion stamp (D-082): lands even when every candidate failed (per-posting
        # isolation — the run itself finished) or the batch raised; only a hard process kill
        # skips it, which the /api/me staleness guard covers.
        mark_backfill_completed(engine, profile.id)
    return MatchingSummary(
        vertical=vertical,
        profiles=1,
        total=total,
        matched=matched,
        failed=total - matched,
        est_cost_usd=cost_usd,
        usage=usage,
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
    load_dotenv()  # load provider credentials + model routes before constructing the LLM client
    engine = get_engine()
    verticals = [args.vertical] if args.vertical else available_verticals()
    for vertical in verticals:
        cfg = load_vertical_config(vertical)
        summary = run_matching(engine, vertical, config=cfg)
        estimated_cost = (
            f"${summary.est_cost_usd:.4f}" if summary.est_cost_usd is not None else "unavailable"
        )
        print(
            f"[{summary.vertical}] matched {summary.matched}/{summary.total} across "
            f"{summary.profiles} profile(s) (failed {summary.failed}) "
            f"est_cost={estimated_cost}"
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
    load_dotenv()  # load provider credentials + model routes before constructing the LLM client
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
        estimated_cost = (
            f"${summary.est_cost_usd:.4f}" if summary.est_cost_usd is not None else "unavailable"
        )
        print(
            f"[{summary.vertical}→{profile.user_email}] backfilled "
            f"{summary.matched}/{summary.total} (failed {summary.failed}) "
            f"est_cost={estimated_cost}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(match_main())
