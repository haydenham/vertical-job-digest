"""Unit tests for the Layer-3 discovery agent (Phase 10.1) — no network, no real LLM.

Pins Stage-2 validation (the deterministic half): dedup, validate-by-fetch (a clean fetch with ≥1
posting → high-confidence `fetchable`; unsupported ATS / fetch error / zero postings →
`unresolved`), and the Stage-1 orchestration with a faked Anthropic client (research + structuring).
"""

from __future__ import annotations

import types
from typing import Any

import httpx
import pytest
import respx

from vja.discover import (
    CandidateEmployer,
    _CandidateList,
    discover_candidates,
    validate_candidate,
)
from vja.models import AtsType, TokenUsage, Verification

_GH_URL = "https://boards-api.greenhouse.io/v1/boards/newco/jobs?content=true"
_GH_JOB = {"id": 1, "title": "Software Engineer", "absolute_url": "https://x/1", "content": "..."}


def _candidate(**over: Any) -> CandidateEmployer:
    base: dict[str, Any] = {
        "name": "NewCo",
        "careers_url": "https://newco.example/careers",
        "ats_type_guess": "greenhouse",
        "ats_slug_guess": "newco",
    }
    base.update(over)
    return CandidateEmployer(**base)


def test_candidate_defaults_are_permissive() -> None:
    c = CandidateEmployer(name="OnlyName")
    assert c.ats_type_guess == "unknown"
    assert c.ats_slug_guess is None and c.careers_url is None


def test_validate_skips_existing_universe() -> None:
    result = validate_candidate(_candidate(name="Camus Energy, Inc."), {"camus energy"})
    assert result.outcome == "skipped_dup"


def test_validate_unsupported_ats_is_unresolved_layer2() -> None:
    result = validate_candidate(_candidate(ats_type_guess="custom"), set())
    assert result.outcome == "unresolved"
    assert result.ats_type is AtsType.UNKNOWN
    assert result.verification is Verification.LAYER2
    assert "custom" in (result.detail or "")  # the guess is preserved for triage


def test_validate_unknown_ats_string_is_unresolved() -> None:
    result = validate_candidate(_candidate(ats_type_guess="who-knows"), set())
    assert result.outcome == "unresolved"
    assert result.ats_type is AtsType.UNKNOWN


@respx.mock
def test_validate_fetchable_when_real_fetch_returns_postings() -> None:
    route = respx.get(_GH_URL).mock(return_value=httpx.Response(200, json={"jobs": [_GH_JOB]}))

    result = validate_candidate(_candidate(), set())

    assert route.called
    assert result.outcome == "fetchable"
    assert result.ats_type is AtsType.GREENHOUSE
    assert result.ats_slug == "newco"
    assert result.verification is Verification.DETECTED
    assert result.posting_count == 1


@respx.mock
def test_validate_fetch_error_is_unresolved() -> None:
    respx.get(_GH_URL).mock(return_value=httpx.Response(500))

    result = validate_candidate(_candidate(), set())

    assert result.outcome == "unresolved"
    assert result.verification is Verification.LAYER2


@respx.mock
def test_validate_zero_postings_is_unresolved() -> None:
    respx.get(_GH_URL).mock(return_value=httpx.Response(200, json={"jobs": []}))

    result = validate_candidate(_candidate(), set())

    assert result.outcome == "unresolved"
    assert "0 open postings" in (result.detail or "")


# --- Stage 1 orchestration with a faked Anthropic client ---------------------------------------


def _usage(inp: int, out: int) -> types.SimpleNamespace:
    return types.SimpleNamespace(input_tokens=inp, output_tokens=out)


class _FakeMessages:
    def __init__(self, report: str, candidates: list[CandidateEmployer]) -> None:
        self._report = report
        self._candidates = candidates
        self.create_calls = 0
        self.parse_calls = 0

    def create(self, **kwargs: Any) -> Any:
        self.create_calls += 1
        block = types.SimpleNamespace(type="text", text=self._report)
        return types.SimpleNamespace(
            content=[block], stop_reason="end_turn", usage=_usage(1000, 200)
        )

    def parse(self, **kwargs: Any) -> Any:
        self.parse_calls += 1
        return types.SimpleNamespace(
            parsed_output=_CandidateList(candidates=self._candidates), usage=_usage(300, 80)
        )


class _FakeClient:
    def __init__(self, report: str, candidates: list[CandidateEmployer]) -> None:
        self.messages = _FakeMessages(report, candidates)


def test_discover_candidates_runs_both_stages_and_sums_usage() -> None:
    client = _FakeClient("report text", [_candidate(), _candidate(name="Two")])

    candidates, usage = discover_candidates(client, "grid_power_software", {"acme"})  # type: ignore[arg-type]

    assert client.messages.create_calls == 1  # end_turn → no pause_turn continuation
    assert client.messages.parse_calls == 1
    assert [c.name for c in candidates] == ["NewCo", "Two"]
    assert usage == TokenUsage(input=1300, output=280)  # research + structuring summed


def test_discover_candidates_empty_report_skips_structuring() -> None:
    client = _FakeClient("", [_candidate()])

    candidates, usage = discover_candidates(client, "grid_power_software", set())  # type: ignore[arg-type]

    assert candidates == []
    assert client.messages.parse_calls == 0  # no report → no structuring spend
    assert usage == TokenUsage(input=1000, output=200)


@pytest.mark.parametrize("stop", ["pause_turn"])
def test_discover_candidates_resumes_on_pause_turn(stop: str) -> None:
    """A `pause_turn` (server-tool loop cap) re-sends until the model finishes."""

    class _PausingMessages(_FakeMessages):
        def create(self, **kwargs: Any) -> Any:
            self.create_calls += 1
            reason = stop if self.create_calls == 1 else "end_turn"
            block = types.SimpleNamespace(type="text", text=self._report)
            return types.SimpleNamespace(
                content=[block], stop_reason=reason, usage=_usage(500, 100)
            )

    client = _FakeClient("report", [_candidate()])
    client.messages = _PausingMessages("report", [_candidate()])

    candidates, usage = discover_candidates(client, "grid_power_software", set())  # type: ignore[arg-type]

    assert client.messages.create_calls == 2  # paused once, then resumed to end_turn
    assert len(candidates) == 1
    assert usage.input == 500 * 2 + 300  # two research calls + one structuring call
