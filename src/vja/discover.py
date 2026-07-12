"""Layer-3 employer discovery: GPT research -> ATS resolution -> validate -> propose.

The model finds employers, never postings. GPT-5.6 runs three bounded, deliberately-oblique
research waves and a separately budgeted ATS-resolution pass. Deterministic registry fetchers
remain authoritative: only a supported ATS that actually returns postings is persisted as
fetchable. Every other proposal is inert (``unknown``/``layer2``) until human review.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
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

_MODEL = os.environ.get("VJA_DISCOVER_MODEL", "gpt-5.6-terra")
_EFFORT = os.environ.get("VJA_DISCOVER_EFFORT", "medium")
_MAX_USD = float(os.environ.get("VJA_DISCOVER_MAX_USD", "4.0"))
_MAX_CANDIDATES = int(os.environ.get("VJA_DISCOVER_MAX_CANDIDATES", "5"))
_WAVE_MAX_TOOL_CALLS = 5
_ATS_MAX_TOOL_CALLS = 4
_RESEARCH_MAX_TOKENS = 8_000
_STRUCTURE_MAX_TOKENS = 4_096
_ATS_MAX_TOKENS = 2_000
_ATS_TIMEOUT_SECONDS = 120.0
_SEARCH_CALL_USD = 0.01

_PROVIDER_ALIASES = {
    "oracle": "oracle_hcm",
    "oracle hcm": "oracle_hcm",
    "smart recruiters": "smartrecruiters",
}
_PROVIDER_HOST_MARKERS: dict[str, tuple[str, ...]] = {
    "greenhouse": ("greenhouse.io",),
    "lever": ("lever.co",),
    "ashby": ("ashbyhq.com",),
    "workday": ("myworkdayjobs.com",),
    "icims": ("icims.com", "careers-site.com"),
    "workable": ("workable.com",),
    "smartrecruiters": ("smartrecruiters.com",),
    "oracle_hcm": ("oraclecloud.com",),
    "radancy": ("radancy.com", "talentbrew.com"),
    "paylocity": ("paylocity.com",),
    "bamboohr": ("bamboohr.com",),
    "jazzhr": ("applytojob.com",),
    "kula": ("kula.ai",),
    "gusto": ("jobs.gusto.com",),
    "rippling": ("ats.rippling.com",),
    "trinet_hire": ("trinethire.com",),
    "trakstar": ("trakstar.com",),
    "pinpoint": ("pinpointhq.com",),
    "phenom": ("phenompeople.com",),
}

# Standard direct-API prices per token: input, output. Cache reads are 0.1x input and writes
# 1.25x; TokenUsage.cost already applies those multipliers. Unknown overrides are rejected.
_MODEL_RATES: dict[str, tuple[float, float]] = {
    "gpt-5.6-sol": (5.0 / 1_000_000, 30.0 / 1_000_000),
    "gpt-5.6-terra": (2.5 / 1_000_000, 15.0 / 1_000_000),
    "gpt-5.6-luna": (1.0 / 1_000_000, 6.0 / 1_000_000),
}

_WAVES: tuple[tuple[str, str], ...] = (
    (
        "capital ecosystem",
        "Search focused VC, PE, and accelerator portfolio pages for relevant employers.",
    ),
    (
        "industry ecosystem",
        "Search industry conference exhibitors/sponsors, associations, and event participants.",
    ),
    (
        "market adjacency",
        "Search funding announcements, competitors, partners, and newly emerging vendors.",
    ),
)

_RESEARCH_INSTRUCTIONS = """\
You are a sourcing analyst expanding a curated employer universe for a vertical job-intelligence
tool. Find NEW EMPLOYERS (companies that hire), never job postings. Use only the assigned source
wave; do not fall back to model memory. Prefer companies genuinely in the vertical with real US
early-career software/data hiring.

For each promising company, open its careers page or an actual job/apply link. Report exactly:
Company: <display name>
Careers URL: <url or unknown>
ATS: <provider or unknown>
ATS slug/endpoint: <value or unknown>
Category: <short category>
Evidence: <source URLs and one-line fit rationale>

Do not propose a company in the supplied existing/earlier-wave list. A concise evidence-backed
report is more valuable than speculative volume."""

_STRUCTURE_INSTRUCTIONS = """\
Convert the supplied research reports into candidate employers. Deduplicate companies, rank the
strongest vertical fits first, and return no more than the stated limit. Copy ATS evidence; do not
invent a company, URL, provider, slug, or endpoint absent from the reports. Use "unknown" when the
research is unsure."""

_ATS_INSTRUCTIONS = """\
Resolve the applicant-tracking system for exactly one employer. Spend the bounded web allowance
in this order: (1) canonical careers page, (2) an actual job/apply link, (3) a targeted ATS-host
search, (4) one fallback search. A provider is resolved only with a canonical URL that exposes the
company slug or a complete endpoint. Model confidence without URL evidence is unresolved.

Known examples include Greenhouse, Lever, Ashby, Workday, iCIMS/Jibe, Workable, SmartRecruiters,
Oracle HCM, Radancy, and BambooHR. Identify unsupported providers accurately too: their proposals
remain parked until a fetcher exists. Return the strict schema and no prose."""


class CandidateEmployer(BaseModel):
    """Unverified employer emitted by the structured discovery stage."""

    name: str = Field(description="Company display name.")
    careers_url: str | None = Field(default=None, description="Careers page URL, or null.")
    ats_type_guess: str = Field(default="unknown", description="ATS provider identifier.")
    ats_slug_guess: str | None = Field(default=None, description="Company ATS slug, or null.")
    endpoint_guess: str | None = Field(default=None, description="Complete ATS endpoint, or null.")
    category: str | None = None
    rationale: str | None = None


class _CandidateList(BaseModel):
    candidates: list[CandidateEmployer] = Field(default_factory=list)


class ATSOutcome(StrEnum):
    RESOLVED_SUPPORTED = "resolved_supported"
    RESOLVED_UNSUPPORTED = "resolved_unsupported"
    CAREERS_PAGE_ONLY = "careers_page_only"
    BLOCKED_OR_JS_RENDERED = "blocked_or_js_rendered"
    NO_JOBS_FOUND = "no_jobs_found"
    UNRESOLVED_BUDGET_EXHAUSTED = "unresolved_budget_exhausted"
    RESOLVER_FAILED = "resolver_failed"


class ATSResolution(BaseModel):
    """Evidence-bearing result of one candidate's bounded GPT resolver call."""

    outcome: ATSOutcome
    provider: str = "unknown"
    ats_slug: str | None = None
    endpoint: str | None = None
    canonical_url: str | None = None
    evidence_urls: list[str] = Field(default_factory=list)
    detail: str = ""


@dataclass(frozen=True)
class ValidationResult:
    candidate: CandidateEmployer
    outcome: str  # fetchable | unresolved | skipped_dup
    ats_type: AtsType = AtsType.UNKNOWN
    ats_slug: str | None = None
    endpoint: str | None = None
    verification: Verification | None = None
    posting_count: int = 0
    detail: str | None = None


@dataclass
class DiscoveryMeter:
    """Provider usage plus hosted-tool counts for one complete run."""

    usage: TokenUsage = field(default_factory=TokenUsage)
    tool_actions: int = 0
    billable_searches: int = 0

    def add_response(self, response: Any) -> None:
        self.usage = self.usage + _openai_usage(getattr(response, "usage", None))
        actions, searches = _count_web_actions(getattr(response, "output", []))
        self.tool_actions += actions
        self.billable_searches += searches

    def cost(self, model: str = _MODEL) -> float:
        in_rate, out_rate = _model_rates(model)
        return self.usage.cost(in_rate, out_rate) + self.billable_searches * _SEARCH_CALL_USD


@dataclass
class DiscoverySummary:
    vertical: str
    candidates: int = 0
    proposed_fetchable: int = 0
    proposed_unresolved: int = 0
    skipped_dup: int = 0
    waves_completed: int = 0
    waves_failed: int = 0
    resolver_attempted: int = 0
    resolver_resolved: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)
    tool_actions: int = 0
    billable_searches: int = 0
    dry_run: bool = False
    model: str = _MODEL

    @property
    def est_cost_usd(self) -> float:
        in_rate, out_rate = _model_rates(self.model)
        return self.usage.cost(in_rate, out_rate) + self.billable_searches * _SEARCH_CALL_USD


@dataclass
class _ReportCheckpoint:
    path: Path | None
    sections: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, vertical_key: str) -> _ReportCheckpoint:
        try:
            out_dir = Path(os.environ.get("VJA_DISCOVER_REPORT_DIR", "data/discovery_reports"))
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
            return cls(out_dir / f"{vertical_key}_{stamp}.md")
        except OSError as exc:
            logger.warning("could not create discovery checkpoint: %s", exc)
            return cls(None)

    def append(self, heading: str, body: str) -> None:
        self.sections.append(f"## {heading}\n\n{body.strip()}\n")
        if self.path is None:
            return
        try:
            self.path.write_text("# Discovery run checkpoint\n\n" + "\n".join(self.sections))
            logger.info("discovery checkpoint updated: %s", self.path)
        except OSError as exc:
            logger.warning("could not update discovery checkpoint: %s", exc)


def _model_rates(model: str) -> tuple[float, float]:
    try:
        return _MODEL_RATES[model]
    except KeyError:
        allowed = ", ".join(sorted(_MODEL_RATES))
        message = f"unsupported VJA_DISCOVER_MODEL={model!r}; choose one of: {allowed}"
        raise ValueError(message) from None


def _openai_usage(usage: Any) -> TokenUsage:
    """Translate Responses usage, whose cached/write counts live under input details."""
    if usage is None:
        return TokenUsage()
    total_input = int(getattr(usage, "input_tokens", 0) or 0)
    details = getattr(usage, "input_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0)
    cache_write = int(getattr(details, "cache_write_tokens", 0) or 0)
    return TokenUsage(
        input=max(0, total_input - cached - cache_write),
        output=int(getattr(usage, "output_tokens", 0) or 0),
        cache_read=cached,
        cache_write=cache_write,
    )


def _count_web_actions(output: Any) -> tuple[int, int]:
    """Return (all web actions, billable search actions) from a completed Response."""
    actions = searches = 0
    for item in output or []:
        if getattr(item, "type", None) != "web_search_call":
            continue
        actions += 1
        action = getattr(item, "action", None)
        if getattr(action, "type", None) == "search":
            searches += 1
    return actions, searches


def _request_response(client: Any, **kwargs: Any) -> Any:
    """Run one complete Response without the SDK's fragile stream accumulator."""
    text_format = kwargs.pop("text_format", None)
    if text_format is not None:
        return client.responses.parse(text_format=text_format, **kwargs)
    return client.responses.create(**kwargs)


def _company_names(report: str) -> set[str]:
    return {
        normalize_employer_name(match.group(1))
        for match in re.finditer(r"(?im)^Company:\s*(.+?)\s*$", report)
    }


def discover_candidates(
    client: Any,
    vertical_key: str,
    existing_names: set[str],
    *,
    limit: int | None = None,
    effort: str = _EFFORT,
    checkpoint: _ReportCheckpoint | None = None,
) -> tuple[list[CandidateEmployer], DiscoveryMeter, int, int]:
    """Run three bounded sourcing waves, then one tool-free structuring call."""
    _model_rates(_MODEL)  # validate override before the first paid request
    cp = checkpoint or _ReportCheckpoint.create(vertical_key)
    meter = DiscoveryMeter()
    reports: list[str] = []
    excluded = set(existing_names)
    completed = failed = 0

    for wave_number, (wave_name, wave_task) in enumerate(_WAVES, 1):
        if meter.cost() >= _MAX_USD:
            cp.append(wave_name, "Skipped: global spend ceiling reached.")
            continue
        universe = "\n".join(f"- {name}" for name in sorted(excluded)) or "(none yet)"
        prompt = (
            f"Vertical: {vertical_key}\nAssigned wave: {wave_name}\n{wave_task}\n\n"
            f"Do not propose these existing/earlier-wave names:\n{universe}"
        )
        label = f"research wave {wave_number}/{len(_WAVES)} ({wave_name})"
        logger.info("starting %s (<=%d web actions)", label, _WAVE_MAX_TOOL_CALLS)
        try:
            response = _request_response(
                client,
                model=_MODEL,
                instructions=_RESEARCH_INSTRUCTIONS,
                input=prompt,
                tools=[{"type": "web_search", "search_context_size": "medium"}],
                max_tool_calls=_WAVE_MAX_TOOL_CALLS,
                max_output_tokens=_RESEARCH_MAX_TOKENS,
                reasoning={"effort": effort},
                store=False,
            )
        except OpenAIError as exc:
            failed += 1
            logger.warning("%s failed after retries: %s", label, exc)
            cp.append(wave_name, f"FAILED after retries: {exc}")
            continue
        meter.add_response(response)
        report = str(getattr(response, "output_text", "") or "").strip()
        if not report:
            failed += 1
            cp.append(wave_name, "FAILED: response contained no report.")
            continue
        completed += 1
        reports.append(f"### {wave_name}\n\n{report}")
        excluded.update(_company_names(report))
        cp.append(
            wave_name,
            f"{report}\n\nCost after wave: ${meter.cost():.4f}; "
            f"web actions: {meter.tool_actions}; searches: {meter.billable_searches}",
        )
        logger.info("finished %s; est $%.4f", label, meter.cost())

    if not reports:
        return [], meter, completed, failed

    candidate_limit = min(_MAX_CANDIDATES, limit) if limit is not None else _MAX_CANDIDATES
    combined = "\n\n".join(reports)
    parsed = client.responses.parse(
        model=_MODEL,
        instructions=_STRUCTURE_INSTRUCTIONS,
        input=f"Candidate limit: {max(0, candidate_limit)}\n\n{combined}",
        text_format=_CandidateList,
        max_output_tokens=_STRUCTURE_MAX_TOKENS,
        store=False,
    )
    meter.add_response(parsed)
    structured = getattr(parsed, "output_parsed", None)
    candidates = list(structured.candidates) if structured is not None else []
    return candidates[: max(0, candidate_limit)], meter, completed, failed


def validate_candidate(candidate: CandidateEmployer, existing_names: set[str]) -> ValidationResult:
    """Deduplicate and require a successful real registry fetch with at least one posting."""
    if normalize_employer_name(candidate.name) in existing_names:
        return ValidationResult(candidate, "skipped_dup")

    guess = _normalize_provider(candidate.ats_type_guess)
    try:
        ats = AtsType(guess)
    except ValueError:
        ats = AtsType.UNKNOWN
    hint = (
        f"agent guess: ats={guess} slug={candidate.ats_slug_guess} "
        f"endpoint={candidate.endpoint_guess} url={candidate.careers_url}"
    )
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
            candidate, "unresolved", verification=Verification.LAYER2, detail=f"{hint}; {exc}"
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


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("-", "_")
    return _PROVIDER_ALIASES.get(normalized, normalized.replace(" ", "_"))


def _provider_url_matches(provider: str, url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    markers = _PROVIDER_HOST_MARKERS.get(provider)
    if markers is not None:
        return any(host == marker or host.endswith(f".{marker}") for marker in markers)
    provider_token = provider.replace("_", "")
    return bool(provider_token) and provider_token in host.replace("-", "").replace("_", "")


def _evidence_is_sufficient(resolution: ATSResolution) -> bool:
    url = resolution.canonical_url or ""
    provider = _normalize_provider(resolution.provider)
    return (
        url.startswith(("https://", "http://"))
        and provider not in {"", "unknown"}
        and _provider_url_matches(provider, url)
        and bool(resolution.ats_slug or resolution.endpoint)
    )


def resolve_candidate_ats(
    client: Any,
    candidate: CandidateEmployer,
    meter: DiscoveryMeter,
    checkpoint: _ReportCheckpoint,
) -> tuple[CandidateEmployer, ATSResolution]:
    """Run one separately bounded resolver and enforce the canonical-URL evidence bar."""
    if meter.cost() >= _MAX_USD:
        resolution = ATSResolution(
            outcome=ATSOutcome.UNRESOLVED_BUDGET_EXHAUSTED,
            detail="global discovery spend ceiling reached before ATS resolution",
        )
        checkpoint.append(f"ATS — {candidate.name}", resolution.model_dump_json(indent=2))
        return candidate, resolution

    prompt = (
        f"Employer: {candidate.name}\nCareers URL: {candidate.careers_url or 'unknown'}\n"
        f"Current ATS guess: {candidate.ats_type_guess}\n"
        f"Current slug: {candidate.ats_slug_guess or 'unknown'}\n"
        f"Current endpoint: {candidate.endpoint_guess or 'unknown'}"
    )
    label = f"ATS resolver ({candidate.name})"
    logger.info("starting %s (<=%d web actions)", label, _ATS_MAX_TOOL_CALLS)
    try:
        response = _request_response(
            client,
            model=_MODEL,
            instructions=_ATS_INSTRUCTIONS,
            input=prompt,
            tools=[{"type": "web_search", "search_context_size": "low"}],
            max_tool_calls=_ATS_MAX_TOOL_CALLS,
            max_output_tokens=_ATS_MAX_TOKENS,
            reasoning={"effort": "low"},
            text_format=ATSResolution,
            timeout=_ATS_TIMEOUT_SECONDS,
            store=False,
        )
        meter.add_response(response)
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ValueError("resolver returned no structured output")
        resolution = parsed
    except (OpenAIError, ValueError) as exc:
        resolution = ATSResolution(outcome=ATSOutcome.RESOLVER_FAILED, detail=str(exc))

    provider = _normalize_provider(resolution.provider)
    if resolution.outcome in {
        ATSOutcome.RESOLVED_SUPPORTED,
        ATSOutcome.RESOLVED_UNSUPPORTED,
    } and not _evidence_is_sufficient(resolution):
        resolution = resolution.model_copy(
            update={
                "outcome": ATSOutcome.CAREERS_PAGE_ONLY,
                "detail": f"insufficient canonical URL/slug evidence; {resolution.detail}".strip(),
            }
        )
    elif resolution.outcome in {
        ATSOutcome.RESOLVED_SUPPORTED,
        ATSOutcome.RESOLVED_UNSUPPORTED,
    }:
        try:
            provider_type = AtsType(provider)
        except ValueError:
            provider_type = AtsType.UNKNOWN
        inferred_outcome = (
            ATSOutcome.RESOLVED_SUPPORTED
            if provider_type in SUPPORTED_ATS_TYPES
            else ATSOutcome.RESOLVED_UNSUPPORTED
        )
        resolution = resolution.model_copy(
            update={"provider": provider, "outcome": inferred_outcome}
        )

    updated = candidate.model_copy(
        update={
            "careers_url": resolution.canonical_url or candidate.careers_url,
            "ats_type_guess": resolution.provider or "unknown",
            "ats_slug_guess": resolution.ats_slug,
            "endpoint_guess": resolution.endpoint,
        }
    )
    checkpoint.append(f"ATS — {candidate.name}", resolution.model_dump_json(indent=2))
    logger.info("finished %s: %s; est $%.4f", label, resolution.outcome.value, meter.cost())
    return updated, resolution


def _resolution_note(resolution: ATSResolution | None) -> str | None:
    if resolution is None:
        return None
    evidence = ", ".join(resolution.evidence_urls) or resolution.canonical_url or "none"
    return (
        f"ats_resolution={resolution.outcome.value} provider={resolution.provider} "
        f"slug={resolution.ats_slug} endpoint={resolution.endpoint} evidence={evidence} "
        f"detail={resolution.detail}"
    )


def _proposal_notes(
    candidate: CandidateEmployer,
    result: ValidationResult,
    resolution: ATSResolution | None = None,
) -> str:
    parts = ["discovered by agent"]
    if candidate.rationale:
        parts.append(candidate.rationale)
    note = _resolution_note(resolution)
    if note:
        parts.append(note)
    if result.outcome == "fetchable":
        parts.append(f"validated: {result.posting_count} open postings")
    elif result.detail:
        parts.append(result.detail)
    return " | ".join(parts)


def run_discovery(
    engine: Engine,
    vertical_key: str,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    client: Any | None = None,
) -> DiscoverySummary:
    """Research, resolve ATSs, validate with registry fetchers, and persist inert proposals."""
    load_vertical_config(vertical_key)
    _model_rates(_MODEL)
    cli = client or OpenAI(max_retries=2)
    existing = existing_employer_names(engine, vertical_key)
    checkpoint = _ReportCheckpoint.create(vertical_key)
    checkpoint.append(
        "Run configuration",
        f"vertical={vertical_key}\nmodel={_MODEL}\nmax_usd={_MAX_USD}\n"
        f"candidate_limit={min(_MAX_CANDIDATES, limit) if limit is not None else _MAX_CANDIDATES}",
    )

    candidates, meter, waves_completed, waves_failed = discover_candidates(
        cli, vertical_key, existing, limit=limit, checkpoint=checkpoint
    )
    summary = DiscoverySummary(
        vertical=vertical_key,
        candidates=len(candidates),
        waves_completed=waves_completed,
        waves_failed=waves_failed,
        dry_run=dry_run,
    )

    for candidate in candidates:
        result = validate_candidate(candidate, existing)
        if result.outcome == "skipped_dup":
            summary.skipped_dup += 1
            continue

        resolution: ATSResolution | None = None
        resolved_candidate = candidate
        if result.outcome != "fetchable":
            if meter.cost() < _MAX_USD:
                summary.resolver_attempted += 1
            resolved_candidate, resolution = resolve_candidate_ats(
                cli, candidate, meter, checkpoint
            )
            if resolution.outcome == ATSOutcome.RESOLVED_SUPPORTED:
                verified = validate_candidate(resolved_candidate, existing)
                if verified.outcome == "fetchable":
                    result = verified
                    summary.resolver_resolved += 1
                else:
                    result = ValidationResult(
                        resolved_candidate,
                        "unresolved",
                        verification=Verification.LAYER2,
                        detail=f"resolved ATS failed deterministic validation: {verified.detail}",
                    )
            else:
                result = ValidationResult(
                    resolved_candidate,
                    "unresolved",
                    verification=Verification.LAYER2,
                    detail=result.detail,
                )

        fetchable = result.outcome == "fetchable"
        if not dry_run:
            inserted = insert_proposed_employer(
                engine,
                vertical=vertical_key,
                name=resolved_candidate.name,
                ats_type=result.ats_type if fetchable else AtsType.UNKNOWN,
                ats_slug=result.ats_slug if fetchable else None,
                endpoint=result.endpoint if fetchable else None,
                careers_url=resolved_candidate.careers_url,
                category=resolved_candidate.category,
                verification=result.verification,
                notes=_proposal_notes(resolved_candidate, result, resolution),
            )
            if inserted is None:
                summary.skipped_dup += 1
                continue
        existing.add(normalize_employer_name(resolved_candidate.name))
        if fetchable:
            summary.proposed_fetchable += 1
        else:
            summary.proposed_unresolved += 1

    summary.usage = meter.usage
    summary.tool_actions = meter.tool_actions
    summary.billable_searches = meter.billable_searches
    checkpoint.append(
        "Final summary",
        f"candidates={summary.candidates}\nfetchable={summary.proposed_fetchable}\n"
        f"unresolved={summary.proposed_unresolved}\nsearches={summary.billable_searches}\n"
        f"tool_actions={summary.tool_actions}\nest_cost=${summary.est_cost_usd:.4f}",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="vja-discover", description="Layer-3 employer discovery.")
    parser.add_argument("--vertical", required=True, help="vertical config key")
    parser.add_argument(
        "--limit", type=int, default=None, help="max candidates to resolve and persist"
    )
    parser.add_argument("--dry-run", action="store_true", help="run + meter but write nothing")
    args = parser.parse_args(argv)

    summary = run_discovery(get_engine(), args.vertical, limit=args.limit, dry_run=args.dry_run)
    prefix = "[dry-run] " if summary.dry_run else ""
    print(
        f"{prefix}discover [{summary.vertical}]: candidates={summary.candidates} "
        f"proposed(fetchable)={summary.proposed_fetchable} "
        f"proposed(unresolved)={summary.proposed_unresolved} skipped_dup={summary.skipped_dup} "
        f"waves(ok/failed)={summary.waves_completed}/{summary.waves_failed} "
        f"ats(attempted/resolved)={summary.resolver_attempted}/{summary.resolver_resolved} "
        f"web(actions/searches)={summary.tool_actions}/{summary.billable_searches} "
        f"est_cost=${summary.est_cost_usd:.4f} "
        f"tokens(in/out/cr/cw)={summary.usage.input}/{summary.usage.output}/"
        f"{summary.usage.cache_read}/{summary.usage.cache_write}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
