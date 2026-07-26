"""Layer-2 LLM extraction (P5.2) — the first model code in the system.

Turns the unstructured postings Stage A kept in-scope into the structured fields matching needs,
using the configured cheap tier (Haiku 4.5 by default — D-005/D-090) through the provider-neutral
LLM boundary for a schema-validated result. Runs only on open postings with `extracted_at IS NULL`
that pass the free Stage-A title gate, so it's the in-scope, uncached remainder — the ~1k backlog
once, then pennies a night. Synchronous calls (latency lands in-process; the absolute spend is
pennies).

Source text per posting: the **list-only** ATSs (Workday, SmartRecruiters, Oracle HCM, Radancy,
Paylocity, Phenom, BambooHR, Rippling —
their list endpoints omit the job description) fetch it lazily, per in-scope survivor, via their
`fetch_detail` (routed by `_DETAIL_RESOLVERS`); every other ATS carries the description in
`raw_payload`.
Either way the raw payload is handed to the model, which extracts from messy input — the point of
all-LLM extraction. That same fetched body is also *kept* for the list-only ATSs (D-095): it is
normalized to plain text and persisted as `postings.description`, since this is the only place
their body is ever in hand.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from vja.dates import normalize_ats_date
from vja.db.engine import begin
from vja.db.postings import (
    ExtractionCandidate,
    postings_needing_extraction,
    save_extraction,
)
from vja.fetchers.bamboohr import BambooHRFetcher
from vja.fetchers.base import ListOnlyFetcher
from vja.fetchers.oracle import OracleFetcher
from vja.fetchers.paylocity import PaylocityFetcher
from vja.fetchers.phenom import PhenomFetcher
from vja.fetchers.radancy import RadancyFetcher
from vja.fetchers.rippling import RipplingFetcher
from vja.fetchers.smartrecruiters import SmartRecruitersFetcher
from vja.fetchers.workday import WorkdayFetcher
from vja.llm import LiteLLMClient, StructuredLLM, StructuredResult, sum_catalog_costs
from vja.models import AtsType, Employer, Level, RemoteType, TokenUsage
from vja.prefilter import PrefilterConfig, passes_prefilter
from vja.scope import ScopeConfig, in_scope
from vja.text import html_to_text

logger = logging.getLogger("vja.extract")

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5"
_MAX_TOKENS = 1024
_MAX_SOURCE_CHARS = 12_000  # ~3-4k tokens; caps a pathologically large payload


def _extract_model() -> str:
    """LiteLLM model route, read at call time so deployments can switch without code changes."""
    return os.environ.get("VJA_EXTRACT_MODEL") or _DEFAULT_MODEL


_SYSTEM_PROMPT = """\
You extract structured fields from a single job posting (given as the raw ATS payload). Report
only what the posting states; use the unknown/empty value when a field is absent — never guess.

Apply these literal rules:
- level is unknown when the posting gives no level, seniority marker, or experience range.
- for a remote role, location is its stated geographic eligibility; use null if none is stated.
- comp_min / comp_max are BOTH null unless the posting states an annual salary figure in US
  dollars. Never convert to an annual figure: an hourly, daily, weekly, monthly, or per-semester
  rate means comp_min and comp_max are null, no matter how easy the arithmetic looks. A figure in
  any other currency (CAD, EUR, GBP, PLN, ...) also means both are null.
- comp_min / comp_max must be the figures written in comp_raw. Never source them from elsewhere in
  the posting: if the compensation text quotes no numbers, both are null.
- posted_at is only a job publication/start date; never use graduation or candidate-eligibility
  dates.

- level: career level. intern | new_grad | early_career | mid | senior | unknown.
- location: primary work location as a short string (e.g. "Houston, TX"), or null if unstated.
- remote: onsite | hybrid | remote | unknown.
- work_auth: any visa / citizenship / clearance requirement stated, as a short phrase; else null.
- stack: technologies/languages/tools named in the posting, as a list of strings ([] if none).
- comp_min / comp_max: annual USD salary bounds as integers, taken from comp_raw; null otherwise.
- comp_raw: the compensation text exactly as written, if any; null otherwise. Always fill this when
  the posting says anything about pay, even when comp_min / comp_max are null.
- posted_at: the posting/start date if present (ISO 8601 preferred); null otherwise."""

# The instruction prefix is stable across every posting in a run, so mark it cacheable. NB: Haiku
# 4.5's minimum cacheable prefix is 4096 tokens and this prompt is well under that, so it likely
# won't trigger today — kept as the correct pattern (the token meter now shows whether it caches).
# The real extraction lever (unique descriptions are uncacheable) is the Batch API, not caching.
DetailResolver = Callable[[Employer, str], dict[str, Any]]
DetailDescriber = Callable[[dict[str, Any]], str | None]

#: The list-only fetchers, instantiated once so the two maps below stay in step.
_LIST_ONLY_FETCHERS: dict[AtsType, ListOnlyFetcher] = {
    AtsType.WORKDAY: WorkdayFetcher(),
    AtsType.SMARTRECRUITERS: SmartRecruitersFetcher(),
    AtsType.ORACLE_HCM: OracleFetcher(),
    AtsType.RADANCY: RadancyFetcher(),
    AtsType.PAYLOCITY: PaylocityFetcher(),
    AtsType.PHENOM: PhenomFetcher(),
    AtsType.BAMBOOHR: BambooHRFetcher(),
    AtsType.RIPPLING: RipplingFetcher(),
}

#: The **list-only** ATSs whose list endpoint omits the job description, keyed to the fetcher method
#: that lazily fetches one posting's full body (called only for in-scope survivors — cost
#: discipline, D-035). Membership here *is* "needs a lazy detail fetch"; every other ATS carries the
#: description in `raw_payload`. One map, so adding a list-only ATS is a one-line wire-up (no `if`).
_DETAIL_RESOLVERS: dict[AtsType, DetailResolver] = {
    ats_type: fetcher.fetch_detail for ats_type, fetcher in _LIST_ONLY_FETCHERS.items()
}

#: The parallel "where does the body live in *that* payload" map (D-095). Only the provider knows,
#: so each fetcher answers for its own shape; extraction keeps the body it already paid to fetch
#: instead of discarding it after the model call.
_DETAIL_DESCRIPTIONS: dict[AtsType, DetailDescriber] = {
    ats_type: fetcher.detail_description for ats_type, fetcher in _LIST_ONLY_FETCHERS.items()
}


def _default_detail_resolver(employer: Employer, external_id: str) -> dict[str, Any]:
    """Route a list-only employer to its ATS's `fetch_detail`. Only called for ATSs in
    `_DETAIL_RESOLVERS` (see `_posting_source`), so the lookup always hits."""
    return _DETAIL_RESOLVERS[employer.ats_type](employer, external_id)


class ExtractedFields(BaseModel):
    """The Layer-2 structured fields — maps 1:1 to the `postings` extracted columns (`docs/04`)."""

    level: Level = Field(description="Career level; 'unknown' if not stated.")
    location: str | None = Field(default=None, description="Primary location, or null.")
    remote: RemoteType = Field(description="Work arrangement; 'unknown' if not stated.")
    work_auth: str | None = Field(
        default=None, description="Visa/citizenship requirement, or null."
    )
    stack: list[str] = Field(default_factory=list, description="Technologies named; [] if none.")
    comp_min: int | None = Field(default=None, description="Annual USD min, or null.")
    comp_max: int | None = Field(default=None, description="Annual USD max, or null.")
    comp_raw: str | None = Field(default=None, description="Compensation text as written, or null.")
    posted_at: str | None = Field(default=None, description="Posting/start date, or null.")


@dataclass(frozen=True)
class ExtractionSummary:
    vertical: str
    total: int
    extracted: int
    failed: int
    est_cost_usd: float | None
    usage: TokenUsage = TokenUsage()


def fields_to_columns(fields: ExtractedFields) -> dict[str, Any]:
    """Map an `ExtractedFields` to `postings` column values (enums → their stored `.value`)."""
    return {
        "level": fields.level.value,
        "location": fields.location,
        "remote": fields.remote.value,
        "work_auth": fields.work_auth,
        "stack": list(fields.stack),
        "comp_min": fields.comp_min,
        "comp_max": fields.comp_max,
        "comp_raw": fields.comp_raw,
        "posted_at": fields.posted_at,
    }


@dataclass(frozen=True)
class _PostingSource:
    """What one posting's payload yields: the model's input, and the body worth keeping.

    Both come from a *single* read of the payload — for a list-only ATS that read is a network
    fetch, so asking for the description separately would double the requests to the board.
    """

    text: str
    #: Plain-text body to persist, or `None` when the row already has one from L1 (D-095).
    description: str | None


def _posting_source(
    candidate: ExtractionCandidate, resolve_detail: DetailResolver
) -> _PostingSource:
    """The raw payload, or — for the list-only ATSs (`_DETAIL_RESOLVERS`) — the lazily-fetched
    detail body, rendered as the model's source text plus the description to store.

    Rich-list ATSs return `description=None`: their body was written straight from the fetcher at
    insert, and `save_extraction` would not overwrite it anyway (L1 wins). The model's input is
    unchanged by any of this — it is still the same JSON blob, so extraction results and the
    prompt cache do not move.
    """
    ats_type = candidate.employer.ats_type
    description: str | None = None
    if ats_type in _DETAIL_RESOLVERS:
        payload: Any = resolve_detail(candidate.employer, candidate.external_id)
        description = html_to_text(_DETAIL_DESCRIPTIONS[ats_type](payload))
    else:
        payload = candidate.raw_payload
    blob = json.dumps(payload, ensure_ascii=False)[:_MAX_SOURCE_CHARS]
    return _PostingSource(text=f"Title: {candidate.title}\n\n{blob}", description=description)


def extract_posting(client: StructuredLLM, source_text: str) -> StructuredResult[ExtractedFields]:
    """One extraction call → validated fields plus catalog-priced, normalized metadata."""
    return client.parse(
        model=_extract_model(),
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        user=source_text,
        response_model=ExtractedFields,
        cache_system=True,
    )


def run_extraction(
    engine: Engine,
    vertical: str,
    *,
    scope: ScopeConfig,
    prefilter: PrefilterConfig,
    client: StructuredLLM | None = None,
    resolve_detail: DetailResolver | None = None,
    now: datetime | None = None,
) -> ExtractionSummary:
    """Extract every in-scope, not-yet-extracted open posting for `vertical`; persist + meter cost.

    Also stamps the durable Stage-B `in_scope` gate (D-043) from the *effective* L1-authoritative
    location (the stored L1 value when present, else the model's read — like `save_extraction`), so
    the "cleaned" dashboard tier can floor on it without re-deriving the geo/level gate in SQL.

    Per-posting isolation: a single posting's failure (Workday detail error, API error, bad parse)
    is logged and skipped — it never aborts the batch. `client`/`resolve_detail` are injected so
    tests run fully offline.
    """
    stamp = now or datetime.now(UTC)
    cli = client or LiteLLMClient()
    detail = resolve_detail or _default_detail_resolver

    candidates = [
        c for c in postings_needing_extraction(engine, vertical) if in_scope(c.title, scope)
    ]
    extracted = 0
    failed = 0
    usage = TokenUsage()
    cost_usd: float | None = 0.0
    for candidate in candidates:
        try:
            source = _posting_source(candidate, detail)
            call = extract_posting(cli, source.text)
        except (
            Exception
        ) as exc:  # deliberate per-posting isolation boundary (logged, not swallowed)
            logger.warning("extraction failed for posting %s: %r", candidate.posting_id, exc)
            failed += 1
            continue
        fields = call.value
        usage = usage + call.usage
        cost_usd = sum_catalog_costs(cost_usd, call.cost_usd)
        columns = fields_to_columns(fields)
        # Compute the durable in_scope gate on the effective (L1-authoritative) location: the stored
        # L1 value wins when present, else the model's read — matching what save_extraction writes.
        effective_location = (
            candidate.location if candidate.location is not None else fields.location
        )
        columns["in_scope"] = passes_prefilter(fields.level.value, effective_location, prefilter)
        # The list-only ATSs' body exists nowhere else — keep it (D-095). `save_extraction` only
        # fills a NULL, so this can never displace a body L1 already stored.
        if source.description is not None:
            columns["description"] = source.description
        with begin(engine) as conn:
            save_extraction(
                conn,
                candidate.posting_id,
                columns,
                model=call.model,
                now=stamp,
                source_updated_at=normalize_ats_date(fields.posted_at),
            )
        extracted += 1

    return ExtractionSummary(
        vertical=vertical,
        total=len(candidates),
        extracted=extracted,
        failed=failed,
        est_cost_usd=cost_usd,
        usage=usage,
    )


def extract_main(argv: list[str] | None = None) -> int:
    """CLI: `vja-extract [--vertical V]` — extract the in-scope backlog + new postings."""
    import argparse

    from vja.db.engine import get_engine
    from vja.verticals import available_verticals, load_vertical_config

    parser = argparse.ArgumentParser(
        prog="vja-extract", description="LLM-extract in-scope postings."
    )
    parser.add_argument("--vertical", default=None, help="limit to one vertical (default: all)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv()  # load provider credentials + model routes before constructing the LLM client
    engine = get_engine()
    verticals = [args.vertical] if args.vertical else available_verticals()
    for vertical in verticals:
        cfg = load_vertical_config(vertical)
        summary = run_extraction(
            engine,
            vertical,
            scope=cfg.scope,
            prefilter=PrefilterConfig(
                locations=cfg.prefilter_locations, levels=cfg.prefilter_levels
            ),
        )
        estimated_cost = (
            f"${summary.est_cost_usd:.4f}" if summary.est_cost_usd is not None else "unavailable"
        )
        print(
            f"[{summary.vertical}] extracted {summary.extracted}/{summary.total} "
            f"(failed {summary.failed}) est_cost={estimated_cost}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(extract_main())
