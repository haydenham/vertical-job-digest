"""Layer-2 LLM extraction (P5.2) — the first model code in the system.

Turns the unstructured postings Stage A kept in-scope into the structured fields matching needs,
using the cheap tier (Haiku 4.5 — D-005 cost discipline) and `client.messages.parse` for a
schema-validated result. Runs only on open postings with `extracted_at IS NULL` that pass the free
Stage-A title gate, so it's the in-scope, uncached remainder — the ~1k backlog once, then pennies a
night. Synchronous calls (latency lands in-process; the absolute spend is pennies).

Source text per posting: for Workday (list-only, D-032) the description is fetched lazily via the
cxs detail endpoint; every other ATS already carries it in `raw_payload`. Either way the raw
payload is handed to the model, which extracts from messy input — the point of all-LLM extraction.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from anthropic import Anthropic
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
from vja.fetchers.workday import WorkdayFetcher
from vja.models import AtsType, Employer, Level, RemoteType
from vja.scope import ScopeConfig, in_scope

logger = logging.getLogger("vja.extract")

_MODEL = (
    "claude-haiku-4-5"  # cheap tier (D-005); bump to Sonnet only if evals show it underperforms
)
_MAX_TOKENS = 1024
_MAX_SOURCE_CHARS = 12_000  # ~3-4k tokens; caps a pathologically large payload
_HAIKU_IN_PER_TOKEN = 1.0 / 1_000_000  # $1 / MTok input
_HAIKU_OUT_PER_TOKEN = 5.0 / 1_000_000  # $5 / MTok output

_SYSTEM_PROMPT = """\
You extract structured fields from a single job posting (given as the raw ATS payload). Report
only what the posting states; use the unknown/empty value when a field is absent — never guess.

- level: career level. intern | new_grad | early_career | mid | senior | unknown.
- location: primary work location as a short string (e.g. "Houston, TX"), or null if unstated.
- remote: onsite | hybrid | remote | unknown.
- work_auth: any visa / citizenship / clearance requirement stated, as a short phrase; else null.
- stack: technologies/languages/tools named in the posting, as a list of strings ([] if none).
- comp_min / comp_max: annual USD salary bounds as integers if given; null otherwise.
- comp_raw: the compensation text exactly as written, if any; null otherwise.
- posted_at: the posting/start date if present (ISO 8601 preferred); null otherwise."""

DetailResolver = Callable[[Employer, str], dict[str, Any]]


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
    est_cost_usd: float


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


def _source_text(candidate: ExtractionCandidate, resolve_detail: DetailResolver) -> str:
    """The text handed to the model: the raw payload (Workday: the lazily-fetched cxs detail)."""
    if candidate.employer.ats_type == AtsType.WORKDAY:
        payload: Any = resolve_detail(candidate.employer, candidate.external_id)
    else:
        payload = candidate.raw_payload
    blob = json.dumps(payload, ensure_ascii=False)[:_MAX_SOURCE_CHARS]
    return f"Title: {candidate.title}\n\n{blob}"


def extract_posting(client: Anthropic, source_text: str) -> tuple[ExtractedFields, float]:
    """One extraction call → (validated fields, estimated USD cost from token usage)."""
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": source_text}],
        output_format=ExtractedFields,
    )
    usage = response.usage
    cost = usage.input_tokens * _HAIKU_IN_PER_TOKEN + usage.output_tokens * _HAIKU_OUT_PER_TOKEN
    fields = response.parsed_output
    if fields is None:  # refusal / unparseable — surface as a failure for this posting
        raise ValueError("extraction returned no parsed output")
    return fields, cost


def run_extraction(
    engine: Engine,
    vertical: str,
    *,
    scope: ScopeConfig,
    client: Anthropic | None = None,
    resolve_detail: DetailResolver | None = None,
    now: datetime | None = None,
) -> ExtractionSummary:
    """Extract every in-scope, not-yet-extracted open posting for `vertical`; persist + meter cost.

    Per-posting isolation: a single posting's failure (Workday detail error, API error, bad parse)
    is logged and skipped — it never aborts the batch. `client`/`resolve_detail` are injected so
    tests run fully offline.
    """
    stamp = now or datetime.now(UTC)
    cli = client or Anthropic()
    detail = resolve_detail or WorkdayFetcher().fetch_detail

    candidates = [
        c for c in postings_needing_extraction(engine, vertical) if in_scope(c.title, scope)
    ]
    extracted = 0
    failed = 0
    cost = 0.0
    for candidate in candidates:
        try:
            fields, call_cost = extract_posting(cli, _source_text(candidate, detail))
        except (
            Exception
        ) as exc:  # deliberate per-posting isolation boundary (logged, not swallowed)
            logger.warning("extraction failed for posting %s: %r", candidate.posting_id, exc)
            failed += 1
            continue
        cost += call_cost
        with begin(engine) as conn:
            save_extraction(
                conn,
                candidate.posting_id,
                fields_to_columns(fields),
                model=_MODEL,
                now=stamp,
                source_updated_at=normalize_ats_date(fields.posted_at),
            )
        extracted += 1

    return ExtractionSummary(
        vertical=vertical,
        total=len(candidates),
        extracted=extracted,
        failed=failed,
        est_cost_usd=cost,
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
    load_dotenv()  # load `.env` (ANTHROPIC_API_KEY) before constructing the Anthropic client
    engine = get_engine()
    verticals = [args.vertical] if args.vertical else available_verticals()
    for vertical in verticals:
        cfg = load_vertical_config(vertical)
        summary = run_extraction(engine, vertical, scope=cfg.scope)
        print(
            f"[{summary.vertical}] extracted {summary.extracted}/{summary.total} "
            f"(failed {summary.failed}) est_cost=${summary.est_cost_usd:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(extract_main())
