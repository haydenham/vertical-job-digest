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


def test_robotics_employers_are_mapped_correctly(migrated_engine: Engine) -> None:
    import_employers_from_csv(migrated_engine, _SEED)
    with migrated_engine.connect() as conn:
        rows = {
            row["name"]: row
            for row in conn.execute(
                select(employers).where(
                    employers.c.name.in_(["Boston Dynamics", "Cobot", "iRobot"])
                )
            ).mappings()
        }

    assert rows["Boston Dynamics"]["vertical"] == "robotics_software"
    assert rows["Boston Dynamics"]["ats_type"] == "workday"
    assert rows["Boston Dynamics"]["endpoint"].endswith("/Boston_Dynamics/jobs")
    assert rows["Cobot"]["ats_type"] == "ashby"
    assert rows["Cobot"]["ats_slug"] == "cobot"
    assert rows["iRobot"]["ats_type"] == "custom"
    assert rows["iRobot"]["verification"] == "layer2"


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
    # + Southwest/Thales Workday config onboards + United Phenom + Honeywell Oracle
    # + Comply365/Vistair BambooHR (D-096, the D-078 item-5 add) = 16. Total 51,
    # of which 8 are Greenhouse, 3 Ashby, 22 Workday, 6 iCIMS/Jibe, 2 Workable,
    # 1 SmartRecruiters (Vitol),
    # 2 Oracle ORC (Southern Company + Honeywell, canonical host found at the 2026-07-12 coverage
    # audit), 1 Radancy (NextEra), and 1 Pinpoint (Aurora) — Phase 8. (Collins/RTX exceeds the ~4000
    # offset cap → Layer 2; iCIMS legacy-portal Alaska/Joby have no Jibe API and Oracle Con Edison
    # fails paginate-or-fail (61 of 62) → Layer 2; Delta/Avature is bot-challenged → Layer 2;
    # NRG/National Grid/L3Harris Radancy bases not yet live-confirmed → parked `proposed`, D-052.)
    # Robotics adds 24 verified Layer-1 rows: 10 Greenhouse, 5 Lever, 8 Ashby, 1 Workday.
    # Trading adds 36 (D-097): 26 Greenhouse, 1 Lever, 4 Ashby, 3 Workday, 2 iCIMS — five of them
    # (Jane Street, DRW, SIG, CME, ICE) are second rows for companies grid already fetches, so the
    # corpus total counts them twice on purpose: one employer row per (vertical, name).
    assert len(fetchable) == 112
    assert sum(1 for e in fetchable if e.ats_type == AtsType.GREENHOUSE) == 44
    assert sum(1 for e in fetchable if e.ats_type == AtsType.LEVER) == 10
    assert sum(1 for e in fetchable if e.ats_type == AtsType.ASHBY) == 15
    assert sum(1 for e in fetchable if e.ats_type == AtsType.WORKDAY) == 26
    assert sum(1 for e in fetchable if e.ats_type == AtsType.ICIMS) == 8
    assert sum(1 for e in fetchable if e.ats_type == AtsType.WORKABLE) == 2
    assert sum(1 for e in fetchable if e.ats_type == AtsType.SMARTRECRUITERS) == 1
    assert sum(1 for e in fetchable if e.ats_type == AtsType.ORACLE_HCM) == 2
    assert sum(1 for e in fetchable if e.ats_type == AtsType.RADANCY) == 1
    assert sum(1 for e in fetchable if e.ats_type == AtsType.PHENOM) == 1
    assert sum(1 for e in fetchable if e.ats_type == AtsType.PINPOINT) == 1
    assert sum(1 for e in fetchable if e.ats_type == AtsType.BAMBOOHR) == 1
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

    assert len(aviation) == 16
    assert by_type[AtsType.GREENHOUSE] == 2
    assert by_type[AtsType.LEVER] == 1
    assert by_type[AtsType.ASHBY] == 1
    assert by_type[AtsType.WORKDAY] == 7  # + Sabre/Amadeus (P8) + Southwest/Thales (D-076)
    assert by_type[AtsType.ICIMS] == 2  # Garmin, SITA (Phase 8)
    assert by_type[AtsType.PHENOM] == 1  # United (D-076)
    assert by_type[AtsType.ORACLE_HCM] == 1  # Honeywell (2026-07-12 coverage audit)
    assert all(e.ats_slug or e.endpoint for e in aviation)  # slug-derived or explicit endpoint


def test_robotics_vertical_is_fetchable_without_code_change(migrated_engine: Engine) -> None:
    """D-004: Robotics resolves entirely through the same config/seed path as prior verticals."""
    import_employers_from_csv(migrated_engine, _SEED)

    robotics = active_fetchable_employers(migrated_engine, vertical="robotics_software")
    by_type = Counter(e.ats_type for e in robotics)

    assert len(robotics) == 24
    assert by_type[AtsType.GREENHOUSE] == 10
    assert by_type[AtsType.LEVER] == 5
    assert by_type[AtsType.ASHBY] == 8
    assert by_type[AtsType.WORKDAY] == 1
    assert all(e.ats_slug or e.endpoint for e in robotics)


def test_trading_vertical_is_fetchable_without_code_change(migrated_engine: Engine) -> None:
    """D-097/D-004: Trading is the fourth vertical to resolve purely from config + seed data."""
    import_employers_from_csv(migrated_engine, _SEED)

    trading = active_fetchable_employers(migrated_engine, vertical="trading_software")
    by_type = Counter(e.ats_type for e in trading)

    assert len(trading) == 36
    assert by_type[AtsType.GREENHOUSE] == 26
    assert by_type[AtsType.LEVER] == 1
    assert by_type[AtsType.ASHBY] == 4
    assert by_type[AtsType.WORKDAY] == 3  # CME (shared with grid), Nasdaq, Cboe
    assert by_type[AtsType.ICIMS] == 2  # SIG, ICE (both shared with grid)
    assert all(e.ats_slug or e.endpoint for e in trading)


def test_cross_vertical_employers_are_independent_rows(migrated_engine: Engine) -> None:
    """D-097: a company curated in two verticals is two rows, keyed on (vertical, name).

    The marquee financial-trading firms are targets in both grid/power (energy desks) and trading,
    and D-064 gives a user exactly one vertical — so each universe carries its own row. The rows
    are independent: same ATS config, separate identity, separate diff.
    """
    import_employers_from_csv(migrated_engine, _SEED)
    shared = ["Jane Street", "Citadel", "DRW", "SIG (Susquehanna)", "CME Group"]
    with migrated_engine.connect() as conn:
        rows = conn.execute(select(employers).where(employers.c.name.in_(shared))).mappings().all()

    by_name: dict[str, set[str]] = {}
    for row in rows:
        by_name.setdefault(row["name"], set()).add(row["vertical"])
    for name in shared:
        assert by_name[name] == {"grid_power_software", "trading_software"}, name

    # Same ATS wiring on both sides — the duplication is curation, not a second integration.
    jane = {r["vertical"]: r for r in rows if r["name"] == "Jane Street"}
    assert jane["trading_software"]["ats_type"] == jane["grid_power_software"]["ats_type"]
    assert jane["trading_software"]["ats_slug"] == jane["grid_power_software"]["ats_slug"]
    assert jane["trading_software"]["id"] != jane["grid_power_software"]["id"]
