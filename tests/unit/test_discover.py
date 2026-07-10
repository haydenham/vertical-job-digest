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

import vja.discover as discover
from vja.discover import (
    CandidateEmployer,
    _CandidateList,
    _count_tool_uses,
    _model_rates,
    discover_candidates,
    validate_candidate,
)
from vja.models import AtsType, TokenUsage, Verification


@pytest.fixture(autouse=True)
def _report_dir(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Route the Stage-1 report checkpoint to a tmp dir so tests never litter the repo."""
    monkeypatch.setenv("VJA_DISCOVER_REPORT_DIR", str(tmp_path / "reports"))


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


# --- Cost/tool guardrails (the fixes for the $7-and-nothing-to-show run) -----------------------


def _tool_block(name: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(type="server_tool_use", name=name)


class _GuardMessages(_FakeMessages):
    """A never-ending (`pause_turn` forever) research loop emitting configurable per-turn usage +
    server-tool blocks — so only the dollar/tool guards can stop it, never `end_turn`."""

    def __init__(
        self,
        report: str,
        candidates: list[CandidateEmployer],
        *,
        per_turn_usage: tuple[int, int],
        tool_blocks: list[types.SimpleNamespace],
    ) -> None:
        super().__init__(report, candidates)
        self._per_turn_usage = per_turn_usage
        self._tool_blocks = tool_blocks
        self.last_kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.create_calls += 1
        self.last_kwargs = kwargs
        content = [types.SimpleNamespace(type="text", text=self._report), *self._tool_blocks]
        return types.SimpleNamespace(
            content=content, stop_reason="pause_turn", usage=_usage(*self._per_turn_usage)
        )


def test_count_tool_uses_counts_server_tool_blocks() -> None:
    content = [
        types.SimpleNamespace(type="text", text="hi"),
        _tool_block("web_search"),
        _tool_block("web_fetch"),
        _tool_block("web_search"),
    ]
    assert _count_tool_uses(content) == (2, 1)


def test_model_rates_are_model_aware() -> None:
    assert _model_rates("claude-sonnet-5") == (3.0 / 1_000_000, 15.0 / 1_000_000)
    assert _model_rates("claude-opus-4-8") == (5.0 / 1_000_000, 25.0 / 1_000_000)
    assert _model_rates("claude-fable-5") == (10.0 / 1_000_000, 50.0 / 1_000_000)
    assert _model_rates("something-unknown") == (3.0 / 1_000_000, 15.0 / 1_000_000)  # fallback


def test_discover_stops_at_dollar_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    """One turn's spend already crosses the ceiling → the loop breaks after that turn, not at
    `_MAX_CONTINUATIONS`. This is the safety net the old loop lacked."""
    monkeypatch.setattr(discover, "_MAX_USD", 2.0)
    monkeypatch.setattr(discover, "_MODEL", "claude-sonnet-5")  # $3/MTok input
    client = _FakeClient("report", [_candidate()])
    # 1M input tokens ≈ $3 at sonnet rates → over the $2 ceiling after a single turn.
    client.messages = _GuardMessages(
        "report", [_candidate()], per_turn_usage=(1_000_000, 0), tool_blocks=[]
    )

    _candidates, _usage = discover_candidates(client, "grid_power_software", set())  # type: ignore[arg-type]

    assert client.messages.create_calls == 1  # stopped by cost, despite stop_reason=pause_turn


def test_discover_stops_at_cumulative_tool_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cumulative counter is the real cap — a single turn that uses the whole search budget
    stops the run (the old per-request `max_uses` reset let it run far past the cap)."""
    monkeypatch.setattr(discover, "_MAX_SEARCHES", 8)
    monkeypatch.setattr(discover, "_MAX_USD", 999.0)  # keep the money guard out of the way
    client = _FakeClient("report", [_candidate()])
    client.messages = _GuardMessages(
        "report",
        [_candidate()],
        per_turn_usage=(100, 20),
        tool_blocks=[_tool_block("web_search")] * 8,  # hits the search budget in one turn
    )

    _candidates, _usage = discover_candidates(client, "grid_power_software", set())  # type: ignore[arg-type]

    assert client.messages.create_calls == 1  # cumulative search budget reached → stop


class _SpyLogger:
    """Records the rendered messages our code passes to `logger.info/warning`. We spy on the module
    logger rather than use `caplog` because the shared pytest suite corrupts global logging state
    (another test leaves the root at WARNING with a stray handler, so INFO records don't propagate);
    a spy pins *what the code logs* deterministically, independent of any logging configuration."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, msg: str, *args: Any) -> None:
        self.messages.append(msg % args if args else msg)

    def warning(self, msg: str, *args: Any) -> None:
        self.messages.append(msg % args if args else msg)


def test_discover_logs_per_turn_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every research turn emits a heartbeat line (turn counter + tool budget + spend), bracketed by
    a start + finished line, so the multi-minute loop isn't a silent black box — the whole point of
    `fix/discover-progress-logging`."""
    monkeypatch.setattr(discover, "_MAX_USD", 999.0)  # let it run to end_turn, not a guard-break
    spy = _SpyLogger()
    monkeypatch.setattr(discover, "logger", spy)
    client = _FakeClient("report", [_candidate()])

    # Pause once then finish → two research turns, so we can assert the counter advances.
    class _TwoTurnMessages(_FakeMessages):
        def create(self, **kwargs: Any) -> Any:
            self.create_calls += 1
            reason = "pause_turn" if self.create_calls == 1 else "end_turn"
            block = types.SimpleNamespace(type="text", text=self._report)
            return types.SimpleNamespace(
                content=[block], stop_reason=reason, usage=_usage(500, 100)
            )

    client.messages = _TwoTurnMessages("report", [_candidate()])

    discover_candidates(client, "grid_power_software", set())  # type: ignore[arg-type]

    turn_lines = [m for m in spy.messages if m.startswith("research turn")]
    assert len(turn_lines) == 2  # one heartbeat per research call
    assert "research turn 1/" in turn_lines[0]
    assert "research turn 2/" in turn_lines[1]
    assert any("starting discovery research for grid_power_software" in m for m in spy.messages)
    assert any(m.startswith("research finished after 2 turn") for m in spy.messages)


def test_discover_passes_cache_control_and_capped_fetch() -> None:
    """Every research call is prompt-cached and the fetch tool caps page size — the two
    non-negotiable cost fixes."""
    client = _FakeClient("report", [_candidate()])
    client.messages = _GuardMessages(
        "report",
        [_candidate()],
        per_turn_usage=(100, 20),
        tool_blocks=[_tool_block("web_search")] * 8,
    )

    discover_candidates(client, "grid_power_software", set())  # type: ignore[arg-type]

    kwargs = client.messages.last_kwargs
    assert kwargs["cache_control"] == {"type": "ephemeral"}
    fetch_tool = next(t for t in kwargs["tools"] if t["name"] == "web_fetch")
    assert fetch_tool["max_content_tokens"] == discover._WEB_FETCH_MAX_CONTENT_TOKENS


def test_discover_checkpoints_report_to_disk(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Research output is written to disk before the structuring turn, so a capped run keeps it."""
    report_dir = tmp_path / "checkpoints"
    monkeypatch.setenv("VJA_DISCOVER_REPORT_DIR", str(report_dir))
    client = _FakeClient("the research report body", [_candidate()])

    discover_candidates(client, "grid_power_software", set())  # type: ignore[arg-type]

    written = list(report_dir.glob("grid_power_software_*.md"))
    assert len(written) == 1
    assert written[0].read_text(encoding="utf-8") == "the research report body"
