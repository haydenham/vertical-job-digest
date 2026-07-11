"""Layer-3 review surface — the human gate that promotes discovery proposals (Phase 10.2).

The discovery agent (`vja.discover`, D-070) writes new employers as `status=proposed`, but
**only `status=active` employers are fetched nightly** (`db.employers.active_fetchable_employers`),
so a proposal is inert until a human approves it. This module is that approval CLI (`vja-review`):

- **approve** a proposal → `active` if its ATS is a supported Layer-1 fetcher (it gets fetched on
  the next nightly run), else → `approved` and **parked** (vetted, but no fetcher yet — it can't be
  pulled until someone resolves its ATS). Fetchability is tested against `SUPPORTED_ATS_TYPES`, the
  exact predicate the nightly fetch uses, so hand-fixing a parked row's `ats_type` and re-approving
  correctly promotes it to `active`.
- **reject** → `retired` (never deleted — mirrors the never-delete posting rule, D-009).
- **list** the proposals awaiting review (or any lifecycle state; `--status approved` is the parked
  queue), optionally filtered by provider evidence.
- **set-ats** validates corrected provider config with a real registry fetch before stamping it;
  lifecycle status is unchanged, so `approve` remains the promotion gate (D-077).

Approve trusts the already-validated `ats_type` — it does not re-fetch. Deferred to later:
auto-approval, a proposal-precision eval, and non-employer `sources` review.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from dotenv import load_dotenv
from sqlalchemy import Engine

from vja.db.employers import (
    EmployerListing,
    get_employer_by_id,
    list_employers_by_status,
    set_employer_status,
    update_employer_ats,
)
from vja.db.engine import get_engine
from vja.fetchers.base import Fetcher, FetchError
from vja.fetchers.registry import SUPPORTED_ATS_TYPES, get_fetcher
from vja.models import AtsType, Employer, EmployerStatus

logger = logging.getLogger("vja.review")


@dataclass(frozen=True)
class ReviewOutcome:
    """Result of one approve/reject action (observability + test assertions)."""

    employer_id: int
    name: str
    ok: bool  # did the action apply? (False = not found, or wrong current status)
    status: EmployerStatus | None  # the resulting status, when ok
    parked: bool = False  # approved-but-unfetchable (no Layer-1 fetcher yet)
    message: str = ""


@dataclass(frozen=True)
class SetAtsOutcome:
    """Result of validating and stamping one proposal's ATS configuration (D-077)."""

    employer_id: int
    name: str
    ok: bool
    posting_count: int = 0
    message: str = ""


def approve_employer(engine: Engine, employer_id: int) -> ReviewOutcome:
    """Promote a proposed/parked employer when its ATS is fetchable."""
    row = get_employer_by_id(engine, employer_id)
    if row is None:
        return ReviewOutcome(employer_id, "", ok=False, status=None, message="not found")
    if row.status not in {EmployerStatus.PROPOSED, EmployerStatus.APPROVED}:
        return ReviewOutcome(
            employer_id,
            row.name,
            ok=False,
            status=row.status,
            message=(
                f"already {row.status.value}; only proposed or parked employers can be approved"
            ),
        )

    if row.ats_type in SUPPORTED_ATS_TYPES:
        set_employer_status(engine, employer_id, EmployerStatus.ACTIVE)
        return ReviewOutcome(
            employer_id,
            row.name,
            ok=True,
            status=EmployerStatus.ACTIVE,
            message="active — fetched on the next nightly run",
        )
    if row.status is EmployerStatus.APPROVED:
        return ReviewOutcome(
            employer_id,
            row.name,
            ok=False,
            status=EmployerStatus.APPROVED,
            parked=True,
            message=f"still parked — no Layer-1 fetcher for ats_type={row.ats_type.value}",
        )
    set_employer_status(engine, employer_id, EmployerStatus.APPROVED)
    return ReviewOutcome(
        employer_id,
        row.name,
        ok=True,
        status=EmployerStatus.APPROVED,
        parked=True,
        message=f"parked — no Layer-1 fetcher for ats_type={row.ats_type.value}; "
        "resolve its ATS to activate",
    )


def set_employer_ats(
    engine: Engine,
    employer_id: int,
    *,
    ats_type: AtsType,
    ats_slug: str | None = None,
    endpoint: str | None = None,
    fetcher: Fetcher | None = None,
    now: datetime | None = None,
) -> SetAtsOutcome:
    """Validate ATS config by fetching >=1 posting, then stamp it without promotion."""
    row = get_employer_by_id(engine, employer_id)
    if row is None:
        return SetAtsOutcome(employer_id, "", ok=False, message="not found")
    if row.status not in {EmployerStatus.PROPOSED, EmployerStatus.APPROVED}:
        return SetAtsOutcome(
            employer_id,
            row.name,
            ok=False,
            message=(
                f"already {row.status.value}; only proposed or parked employers can be corrected"
            ),
        )
    if ats_type not in SUPPORTED_ATS_TYPES:
        return SetAtsOutcome(
            employer_id,
            row.name,
            ok=False,
            message=f"no Layer-1 fetcher for ats_type={ats_type.value}",
        )

    candidate = Employer(
        id=employer_id,
        vertical=row.vertical,
        name=row.name,
        ats_type=ats_type,
        ats_slug=ats_slug,
        endpoint=endpoint,
        careers_url=row.careers_url,
    )
    resolver = fetcher or get_fetcher(ats_type)
    try:
        postings = resolver.fetch(candidate)
    except (FetchError, ValueError) as exc:
        return SetAtsOutcome(
            employer_id, row.name, ok=False, message=f"validation fetch failed: {exc}"
        )
    if not postings:
        return SetAtsOutcome(
            employer_id, row.name, ok=False, message="validation returned zero postings"
        )

    stamp = now or datetime.now(UTC)
    audit_note = (
        f"ats_corrected_at={stamp.isoformat()} ats_type={ats_type.value} "
        f"validated_postings={len(postings)}"
    )
    updated = update_employer_ats(
        engine,
        employer_id,
        ats_type=ats_type,
        ats_slug=ats_slug,
        endpoint=endpoint,
        audit_note=audit_note,
        now=stamp,
    )
    if not updated:
        return SetAtsOutcome(
            employer_id, row.name, ok=False, message="row disappeared before update"
        )
    return SetAtsOutcome(
        employer_id,
        row.name,
        ok=True,
        posting_count=len(postings),
        message=f"verified {len(postings)} posting(s); status remains {row.status.value}",
    )


def reject_employer(engine: Engine, employer_id: int) -> ReviewOutcome:
    """Reject an employer → `retired` (never deleted). Works on proposed or approved rows."""
    row = get_employer_by_id(engine, employer_id)
    if row is None:
        return ReviewOutcome(employer_id, "", ok=False, status=None, message="not found")
    if row.status is EmployerStatus.RETIRED:
        return ReviewOutcome(
            employer_id, row.name, ok=False, status=row.status, message="already retired"
        )
    set_employer_status(engine, employer_id, EmployerStatus.RETIRED)
    return ReviewOutcome(
        employer_id, row.name, ok=True, status=EmployerStatus.RETIRED, message="retired"
    )


def _print_listing(rows: list[EmployerListing], status: EmployerStatus) -> None:
    if not rows:
        print(f"no employers with status={status.value}")
        return
    print(f"{len(rows)} employer(s) with status={status.value}:")
    for r in rows:
        verification = r.verification.value if r.verification else "-"
        print(
            f"  #{r.id}  {r.name}  [{r.vertical}]  "
            f"ats={r.ats_type.value} verification={verification} category={r.category or '-'}"
        )
        if r.careers_url:
            print(f"      {r.careers_url}")
        if r.notes:
            print(f"      note: {r.notes}")


def _print_outcome(outcome: ReviewOutcome, verb: str) -> None:
    mark = "✓" if outcome.ok else "✗"
    label = outcome.name or f"#{outcome.employer_id}"
    print(f"  {mark} {verb} #{outcome.employer_id} {label}: {outcome.message}")


def main(argv: list[str] | None = None) -> int:
    """CLI: `vja-review {list,approve,reject,set-ats}` — proposal review + correction gate."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="vja-review", description="Review and correct discovery-agent employer proposals."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list employers awaiting review (or any status)")
    p_list.add_argument("--vertical", default=None, help="filter to one vertical config key")
    p_list.add_argument(
        "--status",
        default=EmployerStatus.PROPOSED.value,
        choices=[s.value for s in EmployerStatus],
        help="lifecycle state to list (default: proposed; 'approved' = the parked queue)",
    )
    p_list.add_argument(
        "--provider",
        default=None,
        help="filter by provider evidence in notes or the current ats_type",
    )

    p_approve = sub.add_parser("approve", help="approve proposal(s) → active, else parked")
    p_approve.add_argument("ids", type=int, nargs="+", help="employer id(s) to approve")

    p_reject = sub.add_parser("reject", help="reject proposal(s) → retired")
    p_reject.add_argument("ids", type=int, nargs="+", help="employer id(s) to reject")

    p_set_ats = sub.add_parser("set-ats", help="validate and correct one proposal's ATS")
    p_set_ats.add_argument("id", type=int, help="employer id to correct")
    p_set_ats.add_argument(
        "--ats-type",
        required=True,
        choices=sorted(ats.value for ats in SUPPORTED_ATS_TYPES),
        help="registered Layer-1 ATS provider",
    )
    p_set_ats.add_argument("--slug", default=None, help="provider tenant/board slug")
    p_set_ats.add_argument("--endpoint", default=None, help="explicit provider endpoint")

    args = parser.parse_args(argv)
    engine = get_engine()

    if args.command == "list":
        status = EmployerStatus(args.status)
        rows = list_employers_by_status(
            engine, vertical=args.vertical, status=status, provider=args.provider
        )
        _print_listing(rows, status)
        return 0

    if args.command == "set-ats":
        set_outcome = set_employer_ats(
            engine,
            args.id,
            ats_type=AtsType(args.ats_type),
            ats_slug=args.slug,
            endpoint=args.endpoint,
        )
        mark = "✓" if set_outcome.ok else "✗"
        label = set_outcome.name or f"#{set_outcome.employer_id}"
        print(f"  {mark} set-ats #{set_outcome.employer_id} {label}: {set_outcome.message}")
        return 0 if set_outcome.ok else 1

    action = approve_employer if args.command == "approve" else reject_employer
    outcomes = [action(engine, eid) for eid in args.ids]
    for outcome in outcomes:
        _print_outcome(outcome, args.command)
    return 0 if all(o.ok for o in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
