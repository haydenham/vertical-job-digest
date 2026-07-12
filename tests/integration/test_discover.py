"""Integration tests for discovery persistence + orchestration (Phase 10.1) — migrated SQLite.

Pins the DB half: `existing_employer_names` normalizes; `insert_proposed_employer` writes
`proposed` + `agent_discovered` and is idempotent on `UNIQUE(vertical, name)`; and `run_discovery`
(faked LLM, respx-stubbed ATS) lands the right rows and summary counts, and writes nothing on
`--dry-run`.
"""

from __future__ import annotations

import types
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import Engine, func, select

from vja.db.employers import (
    count_employers,
    existing_employer_names,
    insert_proposed_employer,
    normalize_employer_name,
)
from vja.db.engine import begin
from vja.db.schema import employers
from vja.discover import (
    ATSOutcome,
    ATSResolution,
    CandidateEmployer,
    _CandidateList,
    run_discovery,
    validate_candidate,
)
from vja.models import AtsType, EmployerSource, EmployerStatus, Verification

_VERTICAL = "grid_power_software"
_GH_URL = "https://boards-api.greenhouse.io/v1/boards/newco/jobs?content=true"
_GH_JOB = {"id": 1, "title": "Software Engineer", "absolute_url": "https://x/1", "content": "..."}
_BAMBOO_URL = "https://mysteryco.bamboohr.com/careers/list"
_BAMBOO_LIST = {
    "meta": {"totalCount": 1},
    "result": [{"id": "7", "jobOpeningName": "Grid Engineer"}],
}
_PINPOINT_URL = "https://aireon.pinpointhq.com/postings.json"
_PINPOINT_LIST = {
    "data": [
        {
            "id": "490307",
            "title": "Software Engineer",
            "url": "https://aireon.pinpointhq.com/en/postings/public-id",
        }
    ]
}


@pytest.fixture(autouse=True)
def _report_dir(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Route the Stage-1 report checkpoint to a tmp dir so tests never litter the repo."""
    monkeypatch.setenv("VJA_DISCOVER_REPORT_DIR", str(tmp_path / "reports"))


def _seed_manual(engine: Engine, name: str) -> None:
    with begin(engine) as conn:
        conn.execute(
            employers.insert().values(
                vertical=_VERTICAL,
                name=name,
                ats_type="greenhouse",
                source="manual",
                status="active",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )


def test_existing_employer_names_normalizes(migrated_engine: Engine) -> None:
    _seed_manual(migrated_engine, "Camus Energy, Inc.")
    names = existing_employer_names(migrated_engine, _VERTICAL)
    assert names == {normalize_employer_name("Camus Energy, Inc.")} == {"camus energy"}


def test_insert_proposed_employer_writes_and_is_idempotent(migrated_engine: Engine) -> None:
    new_id = insert_proposed_employer(
        migrated_engine,
        vertical=_VERTICAL,
        name="Fluence Grid",
        ats_type=AtsType.GREENHOUSE,
        ats_slug="fluencegrid",
        verification=Verification.DETECTED,
        notes="discovered by agent",
    )
    assert isinstance(new_id, int)

    with migrated_engine.connect() as conn:
        row = conn.execute(
            select(employers.c.status, employers.c.source, employers.c.verification).where(
                employers.c.id == new_id
            )
        ).one()
    assert row.status == EmployerStatus.PROPOSED.value
    assert row.source == EmployerSource.AGENT_DISCOVERED.value
    assert row.verification == Verification.DETECTED.value

    # second call with the same (vertical, name) is a no-op → None, no duplicate row
    again = insert_proposed_employer(
        migrated_engine, vertical=_VERTICAL, name="Fluence Grid", ats_type=AtsType.UNKNOWN
    )
    assert again is None
    assert count_employers(migrated_engine, _VERTICAL) == 1


@respx.mock
def test_validate_candidate_recognizes_supported_pinpoint_board() -> None:
    respx.get(_PINPOINT_URL).mock(return_value=httpx.Response(200, json=_PINPOINT_LIST))
    candidate = CandidateEmployer(name="Aireon", ats_type_guess="pinpoint", ats_slug_guess="aireon")

    result = validate_candidate(candidate, set())

    assert result.outcome == "fetchable"
    assert result.ats_type is AtsType.PINPOINT
    assert result.posting_count == 1


def _fake_client(candidates: list[CandidateEmployer]) -> Any:
    details = types.SimpleNamespace(cached_tokens=0, cache_write_tokens=0)

    def response(*, text: str = "", parsed: Any = None) -> Any:
        return types.SimpleNamespace(
            output_text=text,
            output_parsed=parsed,
            output=[],
            usage=types.SimpleNamespace(
                input_tokens=1_000,
                output_tokens=200,
                input_tokens_details=details,
            ),
        )

    class _Responses:
        def __init__(self) -> None:
            self.wave = 0

        def create(self, **_kwargs: Any) -> Any:
            self.wave += 1
            return response(text=f"Company: Wave{self.wave}\nEvidence: https://source")

        def parse(self, **kwargs: Any) -> Any:
            if kwargs.get("text_format") is ATSResolution:
                resolution = ATSResolution(
                    outcome=ATSOutcome.RESOLVED_UNSUPPORTED,
                    provider="bamboohr",
                    ats_slug="mysteryco",
                    canonical_url="https://mysteryco.bamboohr.com/careers",
                    evidence_urls=["https://mysteryco.bamboohr.com/careers"],
                )
                return response(parsed=resolution)
            return response(parsed=_CandidateList(candidates=candidates))

    return types.SimpleNamespace(responses=_Responses())


def _candidates() -> list[CandidateEmployer]:
    return [
        CandidateEmployer(name="NewCo", ats_type_guess="greenhouse", ats_slug_guess="newco"),
        CandidateEmployer(name="MysteryCo", ats_type_guess="custom"),
        CandidateEmployer(name="Camus Energy", ats_type_guess="greenhouse", ats_slug_guess="c"),
    ]


@respx.mock
def test_run_discovery_persists_proposals(migrated_engine: Engine) -> None:
    respx.get(_GH_URL).mock(return_value=httpx.Response(200, json={"jobs": [_GH_JOB]}))
    respx.get(_BAMBOO_URL).mock(return_value=httpx.Response(200, json=_BAMBOO_LIST))
    _seed_manual(migrated_engine, "Camus Energy")  # the dup

    summary = run_discovery(migrated_engine, _VERTICAL, client=_fake_client(_candidates()))

    assert summary.candidates == 3
    assert summary.proposed_fetchable == 2
    assert summary.proposed_unresolved == 0
    assert summary.skipped_dup == 1
    assert summary.est_cost_usd > 0  # Terra tokens are metered across waves + structuring/resolver

    with migrated_engine.connect() as conn:
        proposed = conn.execute(
            select(employers.c.name, employers.c.ats_type, employers.c.verification)
            .where(employers.c.status == EmployerStatus.PROPOSED.value)
            .order_by(employers.c.name)
        ).all()
    assert [(r.name, r.ats_type, r.verification) for r in proposed] == [
        ("MysteryCo", AtsType.BAMBOOHR.value, Verification.DETECTED.value),
        ("NewCo", AtsType.GREENHOUSE.value, Verification.DETECTED.value),
    ]


@respx.mock
def test_run_discovery_dry_run_writes_nothing(migrated_engine: Engine) -> None:
    respx.get(_GH_URL).mock(return_value=httpx.Response(200, json={"jobs": [_GH_JOB]}))
    respx.get(_BAMBOO_URL).mock(return_value=httpx.Response(200, json=_BAMBOO_LIST))

    summary = run_discovery(
        migrated_engine, _VERTICAL, dry_run=True, client=_fake_client(_candidates()[:2])
    )

    assert summary.dry_run is True
    assert summary.proposed_fetchable == 2 and summary.proposed_unresolved == 0
    with migrated_engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(employers)).scalar_one()
    assert total == 0  # nothing persisted
