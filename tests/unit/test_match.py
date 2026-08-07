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

from vja.db.matches import MatchCandidate
from vja.llm import StructuredLLM, StructuredResult
from vja.match import (
    MatchResult,
    _posting_text,
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
    resume_actions=["Lead with the dispatch simulator; they call it 'grid optimization'."],
    application_notes=["Name the missing production OR experience before they ask."],
)


def _candidate(description: str | None = None) -> MatchCandidate:
    return MatchCandidate(
        posting_id=1,
        title="Software Engineer",
        level="new_grad",
        location="Austin, TX",
        remote=None,
        work_auth=None,
        stack=["Python"],
        comp_min=None,
        comp_max=None,
        comp_raw=None,
        description=description,
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


def test_fields_to_columns_maps_advice_lists_to_json() -> None:
    cols = fields_to_columns(_RESULT)
    assert json.loads(cols["resume_actions"]) == _RESULT.resume_actions
    assert json.loads(cols["application_notes"]) == _RESULT.application_notes


def test_empty_advice_is_stored_as_an_empty_list_not_null() -> None:
    """An impossible role legitimately has no advice, and the prompt says to return nothing.

    That stores as `"[]"` rather than NULL: the two look identical to a reader but mean different
    things in the DB — `"[]"` is *this* model's judgment, NULL is a row matched before D-111.
    Storing None here would erase that distinction at the only point it can be recorded.
    """
    barren = MatchResult(
        verdict=Verdict.NO,
        score=8,
        fits=["Early-career level fits"],
        gaps=["Reactor engineering is a different discipline entirely"],
        rationale="Nothing on your resume bridges software to nuclear plant operations.",
    )
    cols = fields_to_columns(barren)
    assert cols["resume_actions"] == "[]"
    assert cols["application_notes"] == "[]"


def test_match_result_defaults_advice_to_empty_when_the_model_omits_it() -> None:
    """The advice fields are optional at the boundary while fits/gaps stay required (D-007).

    A model that returns nothing for a hopeless role is obeying the prompt, so omission must not
    fail the whole paid result the way a missing `fits` does.
    """
    payload = _RESULT.model_dump()
    del payload["resume_actions"]
    del payload["application_notes"]
    parsed = MatchResult.model_validate(payload)
    assert parsed.resume_actions == []
    assert parsed.application_notes == []

    missing_fits = {k: v for k, v in _RESULT.model_dump().items() if k != "fits"}
    with pytest.raises(ValidationError):
        MatchResult.model_validate(missing_fits)


def test_posting_text_includes_the_description_head_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The body reaches the model, capped, and the cap keeps the *head*.

    Head not tail: a posting front-loads responsibilities and back-loads boilerplate, so the
    truncation must drop the end. A tail-keeping implementation would pass this file's assertions
    on length while feeding the model the EEO statement instead of the job.
    """
    monkeypatch.setenv("VJA_MATCH_DESCRIPTION_CHARS", "40")
    body = "You will build data pipelines in Python. " + "EEO boilerplate. " * 50
    text = _posting_text(_candidate(description=body))

    assert "Description:" in text
    assert "You will build data pipelines in Python." in text  # the head survived
    assert "EEO boilerplate" not in text  # the tail was dropped
    assert body[:40] in text


def test_posting_text_omits_the_description_when_there_is_none() -> None:
    """Rows whose body was never captured (D-095 fills forward) still match, just without it."""
    text = _posting_text(_candidate(description=None))
    assert "Description:" not in text
    assert "Title: Software Engineer" in text


def test_description_budget_defaults_and_is_env_overridable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_body = "x" * 9000
    assert len(_posting_text(_candidate(description=long_body))) < 4200  # ~4000-char default

    monkeypatch.setenv("VJA_MATCH_DESCRIPTION_CHARS", "100")
    assert len(_posting_text(_candidate(description=long_body))) < 300


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
