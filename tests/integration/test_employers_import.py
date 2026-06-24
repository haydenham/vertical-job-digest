"""Employer seed import: real CSV loads correctly and is idempotent (Block 1)."""

import csv
from collections import Counter
from pathlib import Path

from sqlalchemy import Engine, select

from vja.db.employers import (
    active_fetchable_employers,
    count_employers,
    import_employers_from_csv,
)
from vja.db.schema import employers
from vja.fetchers.registry import SUPPORTED_ATS_TYPES
from vja.models import AtsType, Verification

_SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "employers_seed.csv"


def _csv_stats() -> tuple[int, int]:
    """(total data rows, unique (vertical,name) pairs) in the seed CSV."""
    with _SEED.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    pairs = {(r["vertical"].strip(), r["name"].strip()) for r in rows}
    return len(rows), len(pairs)


def test_import_loads_the_full_seed(migrated_engine: Engine) -> None:
    n_rows, n_unique = _csv_stats()
    result = import_employers_from_csv(migrated_engine, _SEED)

    assert count_employers(migrated_engine) == n_unique
    assert result.inserted == n_unique
    assert result.inserted + result.updated == n_rows


def test_known_employer_is_mapped_correctly(migrated_engine: Engine) -> None:
    import_employers_from_csv(migrated_engine, _SEED)
    with migrated_engine.connect() as conn:
        row = (
            conn.execute(select(employers).where(employers.c.name == "Camus Energy"))
            .mappings()
            .first()
        )
    assert row is not None
    assert row["ats_type"] == "greenhouse"
    assert row["ats_slug"] == "camusenergy"
    assert row["verification"] == "verified"
    assert row["created_at"] is not None


def test_reimport_is_idempotent(migrated_engine: Engine) -> None:
    import_employers_from_csv(migrated_engine, _SEED)
    before = count_employers(migrated_engine)

    second = import_employers_from_csv(migrated_engine, _SEED)

    assert count_employers(migrated_engine) == before  # no duplication
    assert second.inserted == 0
    assert second.updated >= 1


def test_all_verification_values_are_in_the_enum(migrated_engine: Engine) -> None:
    import_employers_from_csv(migrated_engine, _SEED)
    with migrated_engine.connect() as conn:
        values = {r[0] for r in conn.execute(select(employers.c.verification).distinct())}
    allowed = {Verification.VERIFIED, Verification.DETECTED, Verification.LAYER2, None}
    assert values <= allowed


def test_unrecognized_ats_type_coerces_to_unknown(migrated_engine: Engine, tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.csv"
    bogus.write_text("vertical,name,ats_type\nexample_vertical,Bogus Co,not_a_real_ats\n")

    result = import_employers_from_csv(migrated_engine, bogus)

    assert result.skipped == 1
    with migrated_engine.connect() as conn:
        row = (
            conn.execute(select(employers).where(employers.c.name == "Bogus Co")).mappings().first()
        )
    assert row is not None
    assert row["ats_type"] == "unknown"


def test_active_fetchable_employers_returns_only_layer1(migrated_engine: Engine) -> None:
    import_employers_from_csv(migrated_engine, _SEED)

    fetchable = active_fetchable_employers(migrated_engine)

    # Grid: 5 Greenhouse + 3 Lever + 1 Ashby + 15 Workday = 24. Aviation (Phase 7): 2 Greenhouse
    # + 1 Lever + 1 Ashby + 3 Workday = 7. Total 31, of which 18 are Workday. (Collins/RTX's whole-
    # conglomerate Workday board exceeds the ~4000 offset cap → reclassified Layer 2; see seed.)
    assert len(fetchable) == 31
    assert sum(1 for e in fetchable if e.ats_type == AtsType.WORKDAY) == 18
    assert all(e.ats_type in SUPPORTED_ATS_TYPES for e in fetchable)
    assert all(e.ats_slug for e in fetchable)  # needed to build endpoints


def test_aviation_vertical_is_fetchable_without_code_change(migrated_engine: Engine) -> None:
    """Phase 7 architecture test (D-004): the aviation vertical resolves to a fetchable subset
    purely from seed data — same code path as grid, no per-vertical branching."""
    import_employers_from_csv(migrated_engine, _SEED)

    aviation = active_fetchable_employers(migrated_engine, vertical="aviation_software")
    by_type = Counter(e.ats_type for e in aviation)

    assert len(aviation) == 7
    assert by_type[AtsType.GREENHOUSE] == 2
    assert by_type[AtsType.LEVER] == 1
    assert by_type[AtsType.ASHBY] == 1
    assert by_type[AtsType.WORKDAY] == 3
    assert all(e.ats_slug for e in aviation)  # Workday endpoints + slug-derived URLs both present
