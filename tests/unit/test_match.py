"""Unit tests for LLM matching (P5.3) — fully offline (the Anthropic client is faked).

Pins the pure pieces: the result→column mapping (lists → JSON text, enum → value), cache-aware
cost math from token usage, the cached-prefix prompt shape, and the no-parsed-output failure path.
The live model runs only in the eval.
"""

import json
from typing import Any, cast
from unittest.mock import call, patch

import pytest
from anthropic import Anthropic
from pydantic import ValidationError

from vja.match import (
    MatchResult,
    _usage_cost,
    fields_to_columns,
    match_posting,
)
from vja.models import Verdict

_RESULT = MatchResult(
    verdict=Verdict.YES,
    score=72,
    fits=["Python + power-market projects", "Early-career level matches"],
    gaps=["No production dispatch-optimization experience"],
    rationale="Strong domain overlap; lacks production OR experience but well within range.",
)


class _FakeUsage:
    def __init__(self) -> None:
        self.input_tokens = 1000
        self.output_tokens = 200
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 4000


class _FakeResponse:
    def __init__(self, parsed: MatchResult | None) -> None:
        self.parsed_output = parsed
        self.usage = _FakeUsage()


class _FakeMessages:
    def __init__(self, parsed: MatchResult | None) -> None:
        self._parsed = parsed
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self._parsed)


class _FakeClient:
    def __init__(self, parsed: MatchResult | None = _RESULT) -> None:
        self.messages = _FakeMessages(parsed)


def test_fields_to_columns_maps_lists_to_json_and_enum_to_value() -> None:
    cols = fields_to_columns(_RESULT)
    assert cols["verdict"] == "yes"  # enum → .value
    assert cols["score"] == 72
    assert json.loads(cols["fits"]) == _RESULT.fits  # JSON round-trips the list
    assert json.loads(cols["gaps"]) == _RESULT.gaps
    assert cols["rationale"].startswith("Strong domain overlap")
    assert "model_version" not in cols  # stamped by save_match, not here


def test_match_result_normalizes_out_of_range_scores_and_logs() -> None:
    payload = _RESULT.model_dump()
    with patch("vja.match.logger.warning") as warning:
        below = MatchResult.model_validate({**payload, "score": -5})
        unchanged = MatchResult.model_validate({**payload, "score": 72})
        above = MatchResult.model_validate({**payload, "score": 105})

    assert below.score == 0
    assert unchanged.score == 72
    assert above.score == 100
    assert warning.call_args_list == [
        call("normalized match score %d → %d", -5, 0),
        call("normalized match score %d → %d", 105, 100),
    ]


def test_match_result_does_not_repair_wrong_score_type() -> None:
    payload = _RESULT.model_dump()
    with pytest.raises(ValidationError):
        MatchResult.model_validate({**payload, "score": "not-a-score"})


def test_match_posting_returns_result_and_real_token_usage() -> None:
    client = cast("Anthropic", _FakeClient())
    result, usage = match_posting(client, "resume", ("power markets",), "Title: SWE")
    assert result is _RESULT
    # The meter reads the raw usage fields (D-069), not a proxy.
    assert (usage.input, usage.output, usage.cache_read, usage.cache_write) == (1000, 200, 4000, 0)
    # 1000 in × $3/MTok + 200 out × $15/MTok + 4000 cache_read × 0.1 × $3/MTok
    expected = 1000 * 3e-6 + 200 * 15e-6 + 4000 * 0.1 * 3e-6
    assert _usage_cost(usage) == pytest.approx(expected)


def test_match_posting_passes_effort_default_and_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient()
    match_posting(cast("Anthropic", client), "resume", (), "Title: SWE")
    assert client.messages.calls[0]["output_config"] == {"effort": "medium"}  # D-069 default

    monkeypatch.setenv("VJA_MATCH_EFFORT", "low")
    client2 = _FakeClient()
    match_posting(cast("Anthropic", client2), "resume", (), "Title: SWE")
    assert client2.messages.calls[0]["output_config"] == {"effort": "low"}  # env-overridable knob


def test_cached_system_carries_resume_and_cache_control() -> None:
    client = _FakeClient()
    match_posting(cast("Anthropic", client), "MY RESUME TEXT", ("dispatch",), "Title: SWE")
    call = client.messages.calls[0]
    system = call["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}  # the cached stable prefix
    assert "MY RESUME TEXT" in system[0]["text"]
    assert "dispatch" in system[0]["text"]  # domain vocabulary steers relevance
    assert call["messages"][0]["content"] == "Title: SWE"  # per-posting text is the volatile half


def test_match_posting_raises_on_no_parsed_output() -> None:
    client = cast("Anthropic", _FakeClient(parsed=None))
    with pytest.raises(ValueError, match="no parsed output"):
        match_posting(client, "resume", (), "Title: SWE")
