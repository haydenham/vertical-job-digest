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


def test_new_curated_employers_are_mapped_correctly(migrated_engine: Engine) -> None:
    import_employers_from_csv(migrated_engine, _SEED)
    with migrated_engine.connect() as conn:
        rows = {
            row["name"]: row
            for row in conn.execute(
                select(employers).where(employers.c.name.in_(["SPAN", "The Brattle Group"]))
            ).mappings()
        }

    assert rows["SPAN"]["vertical"] == "grid_power_software"
    assert rows["SPAN"]["ats_type"] == "ashby"
    assert rows["SPAN"]["ats_slug"] == "span"
    assert rows["SPAN"]["status"] == "active"
    assert rows["SPAN"]["verification"] == "verified"
    assert rows["The Brattle Group"]["vertical"] == "grid_power_software"
    assert rows["The Brattle Group"]["ats_type"] == "greenhouse"
    assert rows["The Brattle Group"]["ats_slug"] == "thebrattlegroup"
    assert rows["The Brattle Group"]["status"] == "active"
    assert rows["The Brattle Group"]["verification"] == "verified"


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

    # Grid: 6 Greenhouse + 3 Lever + 2 Ashby + 15 Workday + 4 iCIMS + 2 Workable + 1 SmartRecruiters
    # + 1 Oracle + 1 Radancy + 1 Pinpoint = 36. Aviation: 2 Greenhouse + 1 Lever +
    # 1 Ashby + 5 Workday + 2 iCIMS
    # + Southwest/Thales Workday config onboards + United Phenom + Honeywell Oracle = 15. Total 51,
    # of which 8 are Greenhouse, 3 Ashby, 22 Workday, 6 iCIMS/Jibe, 2 Workable,
    # 1 SmartRecruiters (Vitol),
    # 2 Oracle ORC (Southern Company + Honeywell, canonical host found at the 2026-07-12 coverage
    # audit), 1 Radancy (NextEra), and 1 Pinpoint (Aurora) — Phase 8. (Collins/RTX exceeds the ~4000
    # offset cap → Layer 2; iCIMS legacy-portal Alaska/Joby have no Jibe API and Oracle Con Edison
    # fails paginate-or-fail (61 of 62) → Layer 2; Delta/Avature is bot-challenged → Layer 2;
    # NRG/National Grid/L3Harris Radancy bases not yet live-confirmed → parked `proposed`, D-052.)
    assert len(fetchable) == 51
    assert sum(1 for e in fetchable if e.ats_type == AtsType.GREENHOUSE) == 8
    assert sum(1 for e in fetchable if e.ats_type == AtsType.ASHBY) == 3
    assert sum(1 for e in fetchable if e.ats_type == AtsType.WORKDAY) == 22
    assert sum(1 for e in fetchable if e.ats_type == AtsType.ICIMS) == 6
    assert sum(1 for e in fetchable if e.ats_type == AtsType.WORKABLE) == 2
    assert sum(1 for e in fetchable if e.ats_type == AtsType.SMARTRECRUITERS) == 1
    assert sum(1 for e in fetchable if e.ats_type == AtsType.ORACLE_HCM) == 2
    assert sum(1 for e in fetchable if e.ats_type == AtsType.RADANCY) == 1
    assert sum(1 for e in fetchable if e.ats_type == AtsType.PHENOM) == 1
    assert sum(1 for e in fetchable if e.ats_type == AtsType.PINPOINT) == 1
    assert all(e.ats_type in SUPPORTED_ATS_TYPES for e in fetchable)
    # Every fetchable row can build its endpoint: a slug (GH/Lever/Ashby/Workable/SR) OR an explicit
    # endpoint (Workday/iCIMS/Oracle/Radancy/Pinpoint custom-domain — per-tenant, no slug).
    assert all(e.ats_slug or e.endpoint for e in fetchable)


def test_aviation_vertical_is_fetchable_without_code_change(migrated_engine: Engine) -> None:
    """Phase 7 architecture test (D-004): the aviation vertical resolves to a fetchable subset
    purely from seed data — same code path as grid, no per-vertical branching."""
    import_employers_from_csv(migrated_engine, _SEED)

    aviation = active_fetchable_employers(migrated_engine, vertical="aviation_software")
    by_type = Counter(e.ats_type for e in aviation)

    assert len(aviation) == 15
    assert by_type[AtsType.GREENHOUSE] == 2
    assert by_type[AtsType.LEVER] == 1
    assert by_type[AtsType.ASHBY] == 1
    assert by_type[AtsType.WORKDAY] == 7  # + Sabre/Amadeus (P8) + Southwest/Thales (D-076)
    assert by_type[AtsType.ICIMS] == 2  # Garmin, SITA (Phase 8)
    assert by_type[AtsType.PHENOM] == 1  # United (D-076)
    assert by_type[AtsType.ORACLE_HCM] == 1  # Honeywell (2026-07-12 coverage audit)
    assert all(e.ats_slug or e.endpoint for e in aviation)  # slug-derived or explicit endpoint
