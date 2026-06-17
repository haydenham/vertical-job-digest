"""Employer seed-CSV importer (`docs/04` §1, `docs/06` "a vertical is data").

The seed CSV (`data/seed/employers_seed.csv`) is the import source of truth. Import is
**idempotent**: keyed on `UNIQUE(vertical, name)`, re-running updates rows in place and
never duplicates them — so it's safe to re-run after editing the CSV.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, func, select

from vja.db.engine import begin, get_engine
from vja.db.schema import employers
from vja.fetchers.registry import SUPPORTED_ATS_TYPES
from vja.models import AtsType, Employer, EmployerSource, EmployerStatus, Verification


@dataclass
class ImportResult:
    """Outcome of an import run (observability + test assertions)."""

    inserted: int = 0
    updated: int = 0
    skipped: int = 0  # rows whose ats_type was unrecognized → coerced to UNKNOWN
    by_ats_type: Counter[str] = field(default_factory=Counter)


def _clean(value: str | None) -> str | None:
    """Strip; treat empty string as NULL."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _coerce_int(value: str | None) -> int | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _coerce_status(value: str | None) -> EmployerStatus:
    cleaned = _clean(value)
    try:
        return EmployerStatus(cleaned) if cleaned else EmployerStatus.ACTIVE
    except ValueError:
        return EmployerStatus.ACTIVE


def _coerce_source(value: str | None) -> EmployerSource:
    cleaned = _clean(value)
    try:
        return EmployerSource(cleaned) if cleaned else EmployerSource.MANUAL
    except ValueError:
        return EmployerSource.MANUAL


def _coerce_verification(value: str | None) -> Verification | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    try:
        return Verification(cleaned)
    except ValueError:
        return None


def _row_to_values(row: dict[str, str], now: datetime) -> tuple[dict[str, Any], bool]:
    """Map one CSV row to column values; second item flags an unresolved ats_type."""
    raw_ats = (row.get("ats_type") or "").strip()
    try:
        ats = AtsType(raw_ats)
        ats_unresolved = False
    except ValueError:
        ats = AtsType.UNKNOWN
        ats_unresolved = raw_ats != AtsType.UNKNOWN.value

    values: dict[str, Any] = {
        "vertical": _clean(row.get("vertical")),
        "name": _clean(row.get("name")),
        "tier": _clean(row.get("tier")),
        "category": _clean(row.get("category")),
        "key_cities": _clean(row.get("key_cities")),
        "role_tilt": _clean(row.get("role_tilt")),
        "ats_type": ats,
        "ats_slug": _clean(row.get("ats_slug")),
        "careers_url": _clean(row.get("careers_url")),
        "endpoint": _clean(row.get("endpoint")),
        "source": _coerce_source(row.get("source")),
        "status": _coerce_status(row.get("status")),
        "verification": _coerce_verification(row.get("verification")),
        "early_career_volume_estimate": _coerce_int(row.get("early_career_volume_estimate")),
        "notes": _clean(row.get("notes")),
        "created_at": now,
        "updated_at": now,
    }
    return values, ats_unresolved


def import_employers_from_csv(
    engine: Engine, csv_path: Path, *, now: datetime | None = None
) -> ImportResult:
    """Idempotently upsert every row of `csv_path` into `employers` (keyed on vertical+name)."""
    stamp = now or datetime.now(UTC)
    result = ImportResult()

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    with begin(engine) as conn:
        for row in rows:
            values, ats_unresolved = _row_to_values(row, stamp)
            if not values["vertical"] or not values["name"]:
                continue  # malformed row with no identity — skip silently
            if ats_unresolved:
                result.skipped += 1
            result.by_ats_type[values["ats_type"].value] += 1

            update_values = {k: v for k, v in values.items() if k != "created_at"}
            updated = conn.execute(
                employers.update()
                .where(employers.c.vertical == values["vertical"])
                .where(employers.c.name == values["name"])
                .values(**update_values)
            )
            if updated.rowcount and updated.rowcount > 0:
                result.updated += 1
            else:
                conn.execute(employers.insert().values(**values))
                result.inserted += 1

    return result


def count_employers(engine: Engine, vertical: str | None = None) -> int:
    """Count employer rows, optionally filtered to one vertical."""
    stmt = select(func.count()).select_from(employers)
    if vertical is not None:
        stmt = stmt.where(employers.c.vertical == vertical)
    with engine.connect() as conn:
        return int(conn.execute(stmt).scalar_one())


def distinct_active_verticals(engine: Engine) -> list[str]:
    """Distinct verticals that have ≥1 active employer (drives the per-vertical digest)."""
    stmt = (
        select(employers.c.vertical)
        .where(employers.c.status == EmployerStatus.ACTIVE.value)
        .distinct()
        .order_by(employers.c.vertical)
    )
    with engine.connect() as conn:
        return [row[0] for row in conn.execute(stmt).all()]


def active_fetchable_employers(engine: Engine, vertical: str | None = None) -> list[Employer]:
    """Active employers whose ATS has a Layer-1 fetcher, as lean fetch-facing `Employer`s.

    This is the read side that drives the nightly fetch: only `status = active` rows with a
    `SUPPORTED_ATS_TYPES` ATS are returned (others await Workday/Tier-B/Layer-2).
    """
    stmt = select(
        employers.c.id,
        employers.c.vertical,
        employers.c.name,
        employers.c.ats_type,
        employers.c.ats_slug,
        employers.c.endpoint,
        employers.c.careers_url,
    ).where(
        employers.c.status == EmployerStatus.ACTIVE.value,
        employers.c.ats_type.in_([t.value for t in SUPPORTED_ATS_TYPES]),
    )
    if vertical is not None:
        stmt = stmt.where(employers.c.vertical == vertical)
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        Employer(
            id=row["id"],
            vertical=row["vertical"],
            name=row["name"],
            ats_type=AtsType(row["ats_type"]),
            ats_slug=row["ats_slug"],
            endpoint=row["endpoint"],
            careers_url=row["careers_url"],
        )
        for row in rows
    ]


def main(argv: list[str] | None = None) -> int:
    """CLI: `vja-import-employers <path-to-csv>` — populate the DB from the seed CSV."""
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: vja-import-employers <path-to-csv>", file=sys.stderr)
        return 2
    csv_path = Path(args[0])
    if not csv_path.exists():
        print(f"error: {csv_path} not found", file=sys.stderr)
        return 2

    engine = get_engine()
    result = import_employers_from_csv(engine, csv_path)
    total = count_employers(engine)
    print(
        f"imported {csv_path}: inserted={result.inserted} updated={result.updated} "
        f"ats-unresolved={result.skipped}; employers in db={total}"
    )
    print("by ats_type:", dict(result.by_ats_type))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
