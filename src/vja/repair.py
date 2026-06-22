"""One-time corpus repair (D-043): undo the location clobber, restamp `in_scope`, drop stale rows.

Branch A fixed the pipeline going forward — `location` is now L1-authoritative and `in_scope` is
persisted at extraction. This repairs the *existing* corpus the clobber already damaged, in three
deterministic steps per vertical:

1. **Re-derive `location` from `raw_payload`.** The captured ATS snapshot still has the L1 location
   each fetcher mapped at insert; re-read it and write it back when non-null (the same
   L1-authoritative rule — a null snapshot leaves the existing value, possibly a legitimate model
   fill, untouched). This undoes the nulls extraction wrote over the fetcher's value.
2. **Recompute + persist `in_scope`** for every extracted posting from `passes_prefilter` on the
   repaired location.
3. **Delete `matches` whose posting now fails Stage B** (`in_scope IS NOT TRUE`) — the foreign /
   out-of-level roles that were matched while the gate was geography-blind.

Then the operator runs `vja-match` (billable) to match the genuinely-unmatched in-scope remainder;
the corrected gate keeps the deleted foreign roles from being rematched.

Idempotent and offline: re-running re-derives the same location, recomputes the same flag, and finds
no stale matches the second time. Reads config, writes the DB — no network, no LLM.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine

from vja.db.engine import begin, get_engine
from vja.db.matches import delete_matches_failing_scope
from vja.db.postings import apply_location_repair, postings_for_repair
from vja.models import AtsType
from vja.prefilter import PrefilterConfig, passes_prefilter
from vja.verticals import available_verticals, load_vertical_config

logger = logging.getLogger("vja.repair")


def _location_from_raw(ats_type: AtsType, raw: dict[str, Any]) -> str | None:
    """Re-derive the L1 location from a posting's captured `raw_payload`, per ATS.

    Mirrors the field each fetcher maps at insert (their module docstrings are the source of truth):
    Greenhouse `location.name`, Lever `categories.location`, Ashby `location`, Workday
    `locationsText`. Returns `None` when the snapshot carries no usable location.
    """
    if ats_type is AtsType.GREENHOUSE:
        loc = raw.get("location")
        name = loc.get("name") if isinstance(loc, dict) else None
        return name if isinstance(name, str) and name else None
    if ats_type is AtsType.LEVER:
        cats = raw.get("categories")
        loc = cats.get("location") if isinstance(cats, dict) else None
        return loc if isinstance(loc, str) and loc else None
    if ats_type is AtsType.ASHBY:
        loc = raw.get("location")
        return loc if isinstance(loc, str) and loc else None
    if ats_type is AtsType.WORKDAY:
        loc = raw.get("locationsText")
        return loc if isinstance(loc, str) and loc else None
    return None


@dataclass(frozen=True)
class RepairSummary:
    vertical: str
    postings: int
    locations_repaired: int
    in_scope_true: int
    in_scope_false: int
    matches_deleted: int


def repair_vertical(engine: Engine, vertical: str, *, prefilter: PrefilterConfig) -> RepairSummary:
    """Run the three repair steps for one vertical; return what changed (no LLM, no network)."""
    rows = postings_for_repair(engine, vertical)
    locations_repaired = in_scope_true = in_scope_false = 0
    for row in rows:
        l1 = _location_from_raw(row.ats_type, row.raw_payload)
        # L1-authoritative: a non-null re-derived value wins; a null snapshot keeps the existing
        # value (possibly a model fill). in_scope is recomputed on the resulting effective location.
        effective_location = l1 if l1 is not None else row.location
        new_location = l1 if (l1 is not None and l1 != row.location) else None
        in_scope: bool | None = None
        if row.extracted:
            in_scope = passes_prefilter(row.level, effective_location, prefilter)
            if in_scope:
                in_scope_true += 1
            else:
                in_scope_false += 1
        if new_location is not None:
            locations_repaired += 1
        with begin(engine) as conn:
            apply_location_repair(conn, row.posting_id, location=new_location, in_scope=in_scope)
    matches_deleted = delete_matches_failing_scope(engine, vertical)
    return RepairSummary(
        vertical=vertical,
        postings=len(rows),
        locations_repaired=locations_repaired,
        in_scope_true=in_scope_true,
        in_scope_false=in_scope_false,
        matches_deleted=matches_deleted,
    )


def repair_main(argv: list[str] | None = None) -> int:
    """CLI: `vja-repair [--vertical V]` — re-derive locations, restamp in_scope, drop stale matches.

    Does NOT run matching — re-run `vja-match` afterward to match the in-scope remainder (billable).
    """
    parser = argparse.ArgumentParser(
        prog="vja-repair",
        description="One-time corpus repair: re-derive locations + in_scope, drop stale matches.",
    )
    parser.add_argument("--vertical", default=None, help="limit to one vertical (default: all)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    engine = get_engine()
    verticals = [args.vertical] if args.vertical else available_verticals()
    for vertical in verticals:
        cfg = load_vertical_config(vertical)
        prefilter = PrefilterConfig(locations=cfg.prefilter_locations, levels=cfg.prefilter_levels)
        summary = repair_vertical(engine, vertical, prefilter=prefilter)
        print(
            f"[{summary.vertical}] postings={summary.postings} "
            f"locations_repaired={summary.locations_repaired} "
            f"in_scope(true/false)={summary.in_scope_true}/{summary.in_scope_false} "
            f"matches_deleted={summary.matches_deleted}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(repair_main())
