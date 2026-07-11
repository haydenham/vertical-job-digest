"""Offline unit tests for GPT discovery, ATS resolution, and deterministic validation."""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

import vja.discover as discover
from vja.discover import (
    ATSOutcome,
    ATSResolution,
    CandidateEmployer,
    DiscoveryMeter,
    _CandidateList,
    _count_web_actions,
    _model_rates,
    _openai_usage,
    _ReportCheckpoint,
    discover_candidates,
    resolve_candidate_ats,
    validate_candidate,
)
from vja.models import AtsType, TokenUsage, Verification

_GH_URL = "https://boards-api.greenhouse.io/v1/boards/newco/jobs?content=true"
_GH_JOB = {"id": 1, "title": "Engineer", "absolute_url": "https://x/1", "content": "..."}


@pytest.fixture(autouse=True)
def _report_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VJA_DISCOVER_REPORT_DIR", str(tmp_path / "reports"))


def _candidate(**over: Any) -> CandidateEmployer:
    values: dict[str, Any] = {
        "name": "NewCo",
        "careers_url": "https://newco.example/careers",
        "ats_type_guess": "greenhouse",
        "ats_slug_guess": "newco",
    }
    values.update(over)
    return CandidateEmployer(**values)


def _usage(inp: int = 1_000, out: int = 200, cached: int = 0) -> Any:
    details = types.SimpleNamespace(cached_tokens=cached, cache_write_tokens=0)
    return types.SimpleNamespace(input_tokens=inp, output_tokens=out, input_tokens_details=details)


def _web_action(action: str) -> Any:
    return types.SimpleNamespace(type="web_search_call", action=types.SimpleNamespace(type=action))


def _response(
    *,
    text: str = "",
    parsed: Any = None,
    actions: tuple[str, ...] = ("search",),
    usage: Any = None,
) -> Any:
    return types.SimpleNamespace(
        output_text=text,
        output_parsed=parsed,
        output=[_web_action(a) for a in actions],
        usage=usage or _usage(),
    )


class _Responses:
    def __init__(
        self,
        waves: list[Any],
        candidates: list[CandidateEmployer],
        resolutions: list[ATSResolution] | None = None,
    ) -> None:
        self.waves = list(waves)
        self.candidates = candidates
        self.resolutions = list(resolutions or [])
        self.response_calls: list[dict[str, Any]] = []
        self.parse_calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.response_calls.append(kwargs)
        return self.waves.pop(0)

    def stream(self, **_kwargs: Any) -> Any:
        raise IndexError("list index out of range")

    def parse(self, **kwargs: Any) -> Any:
        self.parse_calls.append(kwargs)
        if kwargs.get("text_format") is ATSResolution:
            resolution = self.resolutions.pop(0)
            return _response(parsed=resolution, text=resolution.model_dump_json())
        return _response(parsed=_CandidateList(candidates=self.candidates), actions=())


class _Client:
    def __init__(
        self,
        waves: list[Any],
        candidates: list[CandidateEmployer],
        resolutions: list[ATSResolution] | None = None,
    ) -> None:
        self.responses = _Responses(waves, candidates, resolutions)


def _three_waves() -> list[Any]:
    return [
        _response(text="Company: Alpha\nEvidence: https://source/alpha"),
        _response(text="Company: Bravo\nEvidence: https://source/bravo"),
        _response(text="Company: Charlie\nEvidence: https://source/charlie"),
    ]


def test_candidate_defaults_are_permissive() -> None:
    candidate = CandidateEmployer(name="OnlyName")
    assert candidate.ats_type_guess == "unknown"
    assert candidate.ats_slug_guess is None and candidate.careers_url is None


def test_model_allowlist_and_rates() -> None:
    assert _model_rates("gpt-5.6-terra") == (2.5 / 1_000_000, 15 / 1_000_000)
    assert _model_rates("gpt-5.6-sol") == (5 / 1_000_000, 30 / 1_000_000)
    assert _model_rates("gpt-5.6-luna") == (1 / 1_000_000, 6 / 1_000_000)
    with pytest.raises(ValueError, match="unsupported VJA_DISCOVER_MODEL"):
        _model_rates("gpt-unknown")


def test_openai_usage_and_web_action_accounting() -> None:
    usage = _openai_usage(_usage(inp=1_000, out=50, cached=400))
    assert usage == TokenUsage(input=600, output=50, cache_read=400)
    assert _count_web_actions([_web_action("search"), _web_action("open_page")]) == (2, 1)
    meter = DiscoveryMeter()
    meter.add_response(
        _response(actions=("search", "find_in_page"), usage=_usage(inp=1_000, out=0))
    )
    assert meter.tool_actions == 2 and meter.billable_searches == 1
    assert meter.cost("gpt-5.6-terra") == pytest.approx(0.0125)


def test_three_waves_are_bounded_structured_and_cross_excluded(tmp_path: Path) -> None:
    candidates = [_candidate(name=f"Co{i}") for i in range(7)]
    client = _Client(_three_waves(), candidates)
    checkpoint = _ReportCheckpoint(tmp_path / "run.md")

    result, meter, completed, failed = discover_candidates(
        client, "grid_power_software", {"existing co"}, checkpoint=checkpoint
    )

    assert len(result) == 5
    assert completed == 3 and failed == 0
    assert len(client.responses.response_calls) == 3
    assert all(call["max_tool_calls"] == 5 for call in client.responses.response_calls)
    assert all(call["store"] is False for call in client.responses.response_calls)
    assert "alpha" in client.responses.response_calls[1]["input"]
    assert "bravo" in client.responses.response_calls[2]["input"]
    assert client.responses.parse_calls[0]["text_format"] is _CandidateList
    assert meter.billable_searches == 3
    report = checkpoint.path.read_text()  # type: ignore[union-attr]
    assert "capital ecosystem" in report and "market adjacency" in report


def test_research_bypasses_sdk_stream_accumulator() -> None:
    """A client-side stream parser failure must not abort otherwise valid research."""
    client = _Client(_three_waves(), [_candidate()])

    candidates, _meter, completed, failed = discover_candidates(
        client, "grid_power_software", set()
    )

    assert [candidate.name for candidate in candidates] == ["NewCo"]
    assert completed == 3 and failed == 0


def test_limit_caps_structuring_and_resolution_candidates() -> None:
    client = _Client(_three_waves(), [_candidate(name=f"Co{i}") for i in range(5)])
    candidates, _meter, _completed, _failed = discover_candidates(
        client, "grid_power_software", set(), limit=2
    )
    assert len(candidates) == 2
    assert "Candidate limit: 2" in client.responses.parse_calls[0]["input"]


def test_spend_ceiling_stops_starting_later_waves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discover, "_MAX_USD", 0.01)
    client = _Client(_three_waves(), [_candidate()])
    _candidates, _meter, completed, failed = discover_candidates(
        client, "grid_power_software", set()
    )
    assert completed == 1 and failed == 0
    assert len(client.responses.response_calls) == 1
    assert len(client.responses.parse_calls) == 1  # preserve the paid first wave


def test_resolver_uses_locked_budget_and_evidence() -> None:
    resolution = ATSResolution(
        outcome=ATSOutcome.RESOLVED_SUPPORTED,
        provider="greenhouse",
        ats_slug="newco",
        canonical_url="https://job-boards.greenhouse.io/newco",
        evidence_urls=["https://job-boards.greenhouse.io/newco"],
    )
    client = _Client([], [], [resolution])
    meter = DiscoveryMeter()
    candidate, actual = resolve_candidate_ats(
        client,
        _candidate(ats_type_guess="unknown", ats_slug_guess=None),
        meter,
        _ReportCheckpoint(None),
    )
    call = client.responses.parse_calls[0]
    assert call["max_tool_calls"] == 4
    assert call["max_output_tokens"] == 2_000
    assert call["reasoning"] == {"effort": "low"}
    assert call["timeout"] == 120.0
    assert actual.outcome is ATSOutcome.RESOLVED_SUPPORTED
    assert candidate.ats_type_guess == "greenhouse" and candidate.ats_slug_guess == "newco"


def test_resolver_downgrades_confidence_without_url_evidence() -> None:
    resolution = ATSResolution(
        outcome=ATSOutcome.RESOLVED_UNSUPPORTED,
        provider="bamboohr",
        ats_slug="newco",
        canonical_url=None,
    )
    client = _Client([], [], [resolution])
    _candidate_result, actual = resolve_candidate_ats(
        client, _candidate(), DiscoveryMeter(), _ReportCheckpoint(None)
    )
    assert actual.outcome is ATSOutcome.CAREERS_PAGE_ONLY
    assert "insufficient canonical" in actual.detail


def test_resolver_derives_support_from_registry_not_model_label() -> None:
    resolution = ATSResolution(
        outcome=ATSOutcome.RESOLVED_SUPPORTED,
        provider="bamboohr",
        ats_slug="newco",
        canonical_url="https://newco.bamboohr.com/careers",
    )
    client = _Client([], [], [resolution])
    _candidate_result, actual = resolve_candidate_ats(
        client, _candidate(), DiscoveryMeter(), _ReportCheckpoint(None)
    )
    assert actual.outcome is ATSOutcome.RESOLVED_UNSUPPORTED


def test_resolver_accepts_applytojob_as_canonical_jazzhr_evidence() -> None:
    """Utilidata's applytojob.com board is canonical JazzHR evidence, not careers-page-only."""
    resolution = ATSResolution(
        outcome=ATSOutcome.RESOLVED_SUPPORTED,
        provider="JazzHR",
        ats_slug="utilidata",
        endpoint="https://utilidata.applytojob.com/apply",
        canonical_url="https://utilidata.applytojob.com/apply",
        evidence_urls=["https://utilidata.applytojob.com/apply"],
    )
    client = _Client([], [], [resolution])

    _candidate_result, actual = resolve_candidate_ats(
        client, _candidate(name="Utilidata"), DiscoveryMeter(), _ReportCheckpoint(None)
    )

    assert actual.provider == "jazzhr"
    assert actual.outcome is ATSOutcome.RESOLVED_UNSUPPORTED


def test_resolver_skips_call_when_global_budget_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discover, "_MAX_USD", 0.0)
    client = _Client([], [])
    _candidate_result, resolution = resolve_candidate_ats(
        client, _candidate(), DiscoveryMeter(), _ReportCheckpoint(None)
    )
    assert resolution.outcome is ATSOutcome.UNRESOLVED_BUDGET_EXHAUSTED
    assert client.responses.response_calls == []
    assert client.responses.parse_calls == []


def test_validate_skips_existing_universe() -> None:
    result = validate_candidate(_candidate(name="Camus Energy, Inc."), {"camus energy"})
    assert result.outcome == "skipped_dup"


def test_validate_unsupported_ats_is_unresolved_layer2() -> None:
    result = validate_candidate(_candidate(ats_type_guess="bamboohr"), set())
    assert result.outcome == "unresolved"
    assert result.ats_type is AtsType.UNKNOWN
    assert result.verification is Verification.LAYER2
    assert "bamboohr" in (result.detail or "")


@respx.mock
def test_validate_fetchable_when_real_fetch_returns_postings() -> None:
    route = respx.get(_GH_URL).mock(return_value=httpx.Response(200, json={"jobs": [_GH_JOB]}))
    result = validate_candidate(_candidate(), set())
    assert route.called
    assert result.outcome == "fetchable"
    assert result.ats_type is AtsType.GREENHOUSE
    assert result.verification is Verification.DETECTED


@respx.mock
def test_validate_zero_postings_is_unresolved() -> None:
    respx.get(_GH_URL).mock(return_value=httpx.Response(200, json={"jobs": []}))
    result = validate_candidate(_candidate(), set())
    assert result.outcome == "unresolved"
    assert "0 open postings" in (result.detail or "")
