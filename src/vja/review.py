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
  queue).

Approve trusts the `ats_type` the agent already stamped — it does not re-fetch. Deferred to later
(out of scope here): auto-approval, a proposal-precision eval, and non-employer `sources` review.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass

from dotenv import load_dotenv
from sqlalchemy import Engine

from vja.db.employers import (
    EmployerListing,
    get_employer_by_id,
    list_employers_by_status,
    set_employer_status,
)
from vja.db.engine import get_engine
from vja.fetchers.registry import SUPPORTED_ATS_TYPES
from vja.models import EmployerStatus

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


def approve_employer(engine: Engine, employer_id: int) -> ReviewOutcome:
    """Promote a `proposed` employer: → `active` if fetchable, else → `approved` (parked)."""
    row = get_employer_by_id(engine, employer_id)
    if row is None:
        return ReviewOutcome(employer_id, "", ok=False, status=None, message="not found")
    if row.status is not EmployerStatus.PROPOSED:
        return ReviewOutcome(
            employer_id,
            row.name,
            ok=False,
            status=row.status,
            message=f"already {row.status.value}; only proposed employers can be approved",
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
    """CLI: `vja-review {list,approve,reject}` — the discovery-proposal approval gate."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="vja-review", description="Approve/reject discovery-agent employer proposals."
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

    p_approve = sub.add_parser("approve", help="approve proposal(s) → active, else parked")
    p_approve.add_argument("ids", type=int, nargs="+", help="employer id(s) to approve")

    p_reject = sub.add_parser("reject", help="reject proposal(s) → retired")
    p_reject.add_argument("ids", type=int, nargs="+", help="employer id(s) to reject")

    args = parser.parse_args(argv)
    engine = get_engine()

    if args.command == "list":
        status = EmployerStatus(args.status)
        rows = list_employers_by_status(engine, vertical=args.vertical, status=status)
        _print_listing(rows, status)
        return 0

    action = approve_employer if args.command == "approve" else reject_employer
    outcomes = [action(engine, eid) for eid in args.ids]
    for outcome in outcomes:
        _print_outcome(outcome, args.command)
    return 0 if all(o.ok for o in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
