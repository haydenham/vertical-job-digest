"""Unit tests for LLM matching (P5.3) — fully offline (the LLM boundary is faked).

Pins the pure pieces: the result→column mapping (lists → JSON text, enum → value), cache-aware
cost math from token usage, the cached-prefix prompt shape, and the no-parsed-output failure path.
The live model runs only in the eval.
"""

import json
from typing import Any, cast
from unittest.mock import call, patch

import pytest
from pydantic import ValidationError

from vja.llm import StructuredLLM, StructuredResult
from vja.match import (
    MatchResult,
    fields_to_columns,
    match_posting,
)
from vja.models import TokenUsage, Verdict

_RESULT = MatchResult(
    verdict=Verdict.YES,
    score=72,
    fits=["Python + power-market projects", "Early-career level matches"],
    gaps=["No production dispatch-optimization experience"],
    rationale="Strong domain overlap; lacks production OR experience but well within range.",
)


class _FakeClient:
    def __init__(self, parsed: MatchResult | None) -> None:
        self._parsed = parsed
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> StructuredResult[MatchResult]:
        self.calls.append(kwargs)
        if self._parsed is None:
            raise ValueError("LLM returned no structured content")
        return StructuredResult(
            value=self._parsed,
            usage=TokenUsage(input=1000, output=200, cache_read=4000),
            cost_usd=0.0072,
            model="claude-sonnet-4-6",
            latency_seconds=0.5,
            request_id="req-match",
        )


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
    call = match_posting(
        cast("StructuredLLM", _FakeClient(_RESULT)),
        "resume",
        ("power markets",),
        "Title: SWE",
    )
    assert call.value is _RESULT
    # The meter reads the raw usage fields (D-069), not a proxy.
    assert (call.usage.input, call.usage.output, call.usage.cache_read) == (1000, 200, 4000)
    assert call.cost_usd == pytest.approx(0.0072)  # catalog cost crosses the boundary unchanged


def test_match_posting_passes_effort_default_and_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient(_RESULT)
    match_posting(cast("StructuredLLM", client), "resume", (), "Title: SWE")
    assert client.calls[0]["model"] == "openai/gpt-5.6-luna"
    assert client.calls[0]["reasoning_effort"] == "low"  # D-090 selected default

    monkeypatch.setenv("VJA_MATCH_EFFORT", "medium")
    client2 = _FakeClient(_RESULT)
    match_posting(cast("StructuredLLM", client2), "resume", (), "Title: SWE")
    assert client2.calls[0]["reasoning_effort"] == "medium"  # env-overridable knob


def test_match_posting_model_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VJA_MATCH_MODEL", "openai/test-match")
    client = _FakeClient(_RESULT)
    match_posting(cast("StructuredLLM", client), "resume", (), "Title: SWE")
    assert client.calls[0]["model"] == "openai/test-match"


def test_cached_system_carries_resume_and_cache_control() -> None:
    client = _FakeClient(_RESULT)
    match_posting(cast("StructuredLLM", client), "MY RESUME TEXT", ("dispatch",), "Title: SWE")
    call = client.calls[0]
    system = call["system"]
    assert call["cache_system"] is True  # boundary applies one provider cache breakpoint
    assert "MY RESUME TEXT" in system
    assert "dispatch" in system  # domain vocabulary steers relevance
    assert call["user"] == "Title: SWE"  # per-posting text is the volatile half


def test_match_posting_raises_on_no_parsed_output() -> None:
    client = _FakeClient(parsed=None)
    with pytest.raises(ValueError, match="no structured content"):
        match_posting(cast("StructuredLLM", client), "resume", (), "Title: SWE")
