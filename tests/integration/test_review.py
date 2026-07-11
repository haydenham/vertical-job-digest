"""Integration tests for the review surface (Phase 10.2) — the human approval gate.

Pins the promote/park/reject transitions and the `vja-review` CLI: approve a fetchable proposal →
`active` (fetched nightly); approve a no-fetcher proposal → `approved` + parked; reject → `retired`;
guard not-found + non-proposed. Fetchability is keyed on `SUPPORTED_ATS_TYPES` (the nightly's own
predicate), not `verification` — so a supported ats_type activates even with a stale layer2 stamp.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, select

from vja.db.employers import (
    active_fetchable_employers,
    get_employer_by_id,
    insert_proposed_employer,
    list_employers_by_status,
)
from vja.db.schema import employers
from vja.fetchers.base import FetchError
from vja.models import AtsType, Employer, EmployerStatus, RawPosting, Verification
from vja.review import approve_employer, main, reject_employer, set_employer_ats

_VERTICAL = "grid_power_software"


class _FakeFetcher:
    ats_type = AtsType.GREENHOUSE

    def __init__(
        self, postings: list[RawPosting] | None = None, error: Exception | None = None
    ) -> None:
        self.postings = postings if postings is not None else [_posting()]
        self.error = error

    def fetch(self, employer: Employer) -> list[RawPosting]:
        if self.error is not None:
            raise self.error
        return self.postings


def _posting() -> RawPosting:
    return RawPosting(
        external_id="1",
        title="Engineer",
        apply_url="https://example.com/jobs/1",
        location="Chicago, IL",
        updated_at=None,
        raw={},
    )


def _propose(
    engine: Engine,
    name: str,
    *,
    ats_type: AtsType,
    verification: Verification | None,
    slug: str | None = None,
) -> int:
    new_id = insert_proposed_employer(
        engine,
        vertical=_VERTICAL,
        name=name,
        ats_type=ats_type,
        ats_slug=slug,
        verification=verification,
    )
    assert new_id is not None
    return new_id


def test_approve_fetchable_goes_active(migrated_engine: Engine) -> None:
    eid = _propose(
        migrated_engine,
        "NewCo",
        ats_type=AtsType.GREENHOUSE,
        verification=Verification.DETECTED,
        slug="newco",
    )
    outcome = approve_employer(migrated_engine, eid)

    assert outcome.ok is True
    assert outcome.status is EmployerStatus.ACTIVE
    assert outcome.parked is False

    row = get_employer_by_id(migrated_engine, eid)
    assert row is not None and row.status is EmployerStatus.ACTIVE
    # now visible to the nightly fetch
    assert any(e.id == eid for e in active_fetchable_employers(migrated_engine, _VERTICAL))


def test_approve_layer2_parks_as_approved(migrated_engine: Engine) -> None:
    eid = _propose(
        migrated_engine, "MysteryCo", ats_type=AtsType.UNKNOWN, verification=Verification.LAYER2
    )
    outcome = approve_employer(migrated_engine, eid)

    assert outcome.ok is True
    assert outcome.status is EmployerStatus.APPROVED
    assert outcome.parked is True
    assert "no Layer-1 fetcher" in outcome.message

    row = get_employer_by_id(migrated_engine, eid)
    assert row is not None and row.status is EmployerStatus.APPROVED
    # parked → structurally excluded from the nightly fetch
    assert active_fetchable_employers(migrated_engine, _VERTICAL) == []


def test_approve_keys_on_ats_type_not_verification(migrated_engine: Engine) -> None:
    # supported ats_type + a stale layer2 stamp → still activates (predicate = SUPPORTED_ATS_TYPES).
    # Also the manual-resolution path: fix a parked row's ats_type, re-propose, approve → active.
    eid = _propose(
        migrated_engine,
        "FixedCo",
        ats_type=AtsType.GREENHOUSE,
        verification=Verification.LAYER2,
        slug="fixedco",
    )
    outcome = approve_employer(migrated_engine, eid)

    assert outcome.ok is True
    assert outcome.status is EmployerStatus.ACTIVE
    assert outcome.parked is False


def test_approve_parked_employer_after_ats_becomes_fetchable(migrated_engine: Engine) -> None:
    """D-077 regression: an approved/parked row must be re-promotable after ATS correction."""
    eid = _propose(
        migrated_engine,
        "ParkedCo",
        ats_type=AtsType.UNKNOWN,
        verification=Verification.LAYER2,
    )
    assert approve_employer(migrated_engine, eid).status is EmployerStatus.APPROVED

    correction = set_employer_ats(
        migrated_engine,
        eid,
        ats_type=AtsType.GREENHOUSE,
        ats_slug="parkedco",
        fetcher=_FakeFetcher(),
    )
    assert correction.ok is True

    outcome = approve_employer(migrated_engine, eid)
    assert outcome.ok is True
    assert outcome.status is EmployerStatus.ACTIVE


def test_set_ats_validates_then_preserves_status_and_appends_audit_note(
    migrated_engine: Engine,
) -> None:
    eid = _propose(
        migrated_engine, "CorrectMe", ats_type=AtsType.UNKNOWN, verification=Verification.LAYER2
    )
    assert approve_employer(migrated_engine, eid).status is EmployerStatus.APPROVED
    stamp = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)

    outcome = set_employer_ats(
        migrated_engine,
        eid,
        ats_type=AtsType.PAYLOCITY,
        endpoint="https://recruiting.paylocity.com/recruiting/jobs/All/uuid/name",
        fetcher=_FakeFetcher(),
        now=stamp,
    )

    assert outcome.ok is True
    assert outcome.posting_count == 1
    with migrated_engine.connect() as conn:
        row = conn.execute(select(employers).where(employers.c.id == eid)).mappings().one()
    assert row["ats_type"] == AtsType.PAYLOCITY.value
    assert row["endpoint"].endswith("/uuid/name")
    assert row["verification"] == Verification.VERIFIED.value
    assert row["status"] == EmployerStatus.APPROVED.value
    assert "ats_corrected_at=2026-07-11T12:00:00+00:00" in row["notes"]


@pytest.mark.parametrize("postings", [[], None])
def test_set_ats_failure_leaves_row_unchanged(
    migrated_engine: Engine, postings: list[RawPosting] | None
) -> None:
    eid = _propose(
        migrated_engine, "NoWriteCo", ats_type=AtsType.UNKNOWN, verification=Verification.LAYER2
    )
    fetcher = (
        _FakeFetcher(postings=[])
        if postings == []
        else _FakeFetcher(error=FetchError("broken endpoint"))
    )

    outcome = set_employer_ats(
        migrated_engine,
        eid,
        ats_type=AtsType.GREENHOUSE,
        ats_slug="no-write",
        fetcher=fetcher,
    )

    assert outcome.ok is False
    row = get_employer_by_id(migrated_engine, eid)
    assert row is not None
    assert row.ats_type is AtsType.UNKNOWN
    assert row.status is EmployerStatus.PROPOSED


def test_set_ats_refuses_unsupported_or_active_employer(migrated_engine: Engine) -> None:
    eid = _propose(
        migrated_engine, "GuardedCo", ats_type=AtsType.UNKNOWN, verification=Verification.LAYER2
    )
    unsupported = set_employer_ats(
        migrated_engine, eid, ats_type=AtsType.JOBVITE, fetcher=_FakeFetcher()
    )
    assert unsupported.ok is False
    assert "no Layer-1 fetcher" in unsupported.message

    with migrated_engine.begin() as conn:
        conn.execute(
            employers.update()
            .where(employers.c.id == eid)
            .values(ats_type=AtsType.GREENHOUSE.value, status=EmployerStatus.ACTIVE.value)
        )
    active = set_employer_ats(
        migrated_engine, eid, ats_type=AtsType.GREENHOUSE, fetcher=_FakeFetcher()
    )
    assert active.ok is False
    assert "already active" in active.message


def test_list_provider_matches_notes_or_current_ats_type(migrated_engine: Engine) -> None:
    paylocity_note = insert_proposed_employer(
        migrated_engine,
        vertical=_VERTICAL,
        name="EvidenceCo",
        ats_type=AtsType.UNKNOWN,
        verification=Verification.LAYER2,
        notes="ats_resolution=resolved_unsupported provider=Paylocity slug=x",
    )
    assert paylocity_note is not None
    current_type = _propose(
        migrated_engine,
        "TypedCo",
        ats_type=AtsType.PAYLOCITY,
        verification=Verification.VERIFIED,
    )
    _propose(migrated_engine, "OtherCo", ats_type=AtsType.UNKNOWN, verification=Verification.LAYER2)

    rows = list_employers_by_status(
        migrated_engine, status=EmployerStatus.PROPOSED, provider="PAYLOCITY"
    )
    assert {row.id for row in rows} == {paylocity_note, current_type}


def test_reject_retires(migrated_engine: Engine) -> None:
    eid = _propose(
        migrated_engine, "BadCo", ats_type=AtsType.GREENHOUSE, verification=Verification.DETECTED
    )
    outcome = reject_employer(migrated_engine, eid)

    assert outcome.ok is True
    assert outcome.status is EmployerStatus.RETIRED
    row = get_employer_by_id(migrated_engine, eid)
    assert row is not None and row.status is EmployerStatus.RETIRED


def test_approve_not_found_is_not_ok(migrated_engine: Engine) -> None:
    outcome = approve_employer(migrated_engine, 9999)
    assert outcome.ok is False
    assert outcome.status is None
    assert outcome.message == "not found"


def test_approve_non_proposed_is_refused(migrated_engine: Engine) -> None:
    eid = _propose(
        migrated_engine, "TwiceCo", ats_type=AtsType.GREENHOUSE, verification=Verification.DETECTED
    )
    assert approve_employer(migrated_engine, eid).ok is True  # → active
    again = approve_employer(migrated_engine, eid)
    assert again.ok is False
    assert "already active" in again.message
    # unchanged
    row = get_employer_by_id(migrated_engine, eid)
    assert row is not None and row.status is EmployerStatus.ACTIVE


def test_list_by_status_filters(migrated_engine: Engine) -> None:
    a = _propose(
        migrated_engine, "Alpha", ats_type=AtsType.GREENHOUSE, verification=Verification.DETECTED
    )
    b = _propose(
        migrated_engine, "Bravo", ats_type=AtsType.UNKNOWN, verification=Verification.LAYER2
    )

    proposed = list_employers_by_status(migrated_engine, status=EmployerStatus.PROPOSED)
    assert {r.id for r in proposed} == {a, b}
    assert list_employers_by_status(migrated_engine, status=EmployerStatus.ACTIVE) == []

    approve_employer(migrated_engine, a)  # → active
    approve_employer(migrated_engine, b)  # → approved (parked)
    active = list_employers_by_status(migrated_engine, status=EmployerStatus.ACTIVE)
    approved = list_employers_by_status(migrated_engine, status=EmployerStatus.APPROVED)
    assert [r.id for r in active] == [a]
    assert [r.id for r in approved] == [b]
    # vertical filter excludes other verticals
    assert list_employers_by_status(migrated_engine, vertical="aviation_software") == []


def test_cli_list_approve_reject(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # the CLI resolves its own engine via get_engine(); point it at the test engine
    monkeypatch.setattr("vja.review.get_engine", lambda: migrated_engine)
    eid = _propose(
        migrated_engine, "CliCo", ats_type=AtsType.GREENHOUSE, verification=Verification.DETECTED
    )

    assert main(["list"]) == 0
    assert "CliCo" in capsys.readouterr().out

    assert main(["approve", str(eid)]) == 0
    assert get_employer_by_id(migrated_engine, eid).status is EmployerStatus.ACTIVE  # type: ignore[union-attr]

    # rejecting an id that no longer qualifies still runs; a bogus id → exit 1
    assert main(["reject", "8888"]) == 1
    out = capsys.readouterr().out
    assert "not found" in out


def test_cli_provider_filter_and_set_ats(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("vja.review.get_engine", lambda: migrated_engine)
    monkeypatch.setattr("vja.review.get_fetcher", lambda ats: _FakeFetcher())
    eid = insert_proposed_employer(
        migrated_engine,
        vertical=_VERTICAL,
        name="CliCorrectionCo",
        ats_type=AtsType.UNKNOWN,
        verification=Verification.LAYER2,
        notes="ats_resolution=resolved_unsupported provider=paylocity slug=tenant",
    )
    assert eid is not None

    assert main(["list", "--provider", "paylocity"]) == 0
    assert "CliCorrectionCo" in capsys.readouterr().out

    endpoint = "https://recruiting.paylocity.com/recruiting/jobs/All/uuid/tenant"
    assert (
        main(
            [
                "set-ats",
                str(eid),
                "--ats-type",
                "paylocity",
                "--endpoint",
                endpoint,
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "verified 1 posting" in output
    row = get_employer_by_id(migrated_engine, eid)
    assert row is not None and row.status is EmployerStatus.PROPOSED

    assert main(["approve", str(eid)]) == 0
    assert get_employer_by_id(migrated_engine, eid).status is EmployerStatus.ACTIVE  # type: ignore[union-attr]
