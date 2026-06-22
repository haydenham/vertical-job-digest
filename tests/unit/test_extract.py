"""Unit tests for LLM extraction (P5.2) — fully offline (the Anthropic client is faked).

Pins the pure pieces: field→column mapping, cost math from token usage, the Workday-vs-other
source selection, and the no-parsed-output failure path. The live model runs only in the eval.
"""

from typing import Any, cast

import pytest
from anthropic import Anthropic

from vja.db.postings import ExtractionCandidate
from vja.extract import (
    ExtractedFields,
    _source_text,
    extract_posting,
    fields_to_columns,
)
from vja.models import AtsType, Employer, Level, RemoteType

_FIELDS = ExtractedFields(
    level=Level.NEW_GRAD,
    location="Houston, TX",
    remote=RemoteType.HYBRID,
    work_auth="US citizenship required",
    stack=["Python", "AWS"],
    comp_min=90000,
    comp_max=120000,
    comp_raw="$90k–$120k",
    posted_at="2026-06-18",
)


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(self, parsed: ExtractedFields | None, usage: _FakeUsage) -> None:
        self.parsed_output = parsed
        self.usage = usage


class _FakeMessages:
    def __init__(self, parsed: ExtractedFields | None) -> None:
        self._parsed = parsed
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self._parsed, _FakeUsage(1000, 150))


class _FakeClient:
    def __init__(self, parsed: ExtractedFields | None = _FIELDS) -> None:
        self.messages = _FakeMessages(parsed)


def _candidate(
    ats: AtsType, *, external_id: str = "x", title: str = "Engineer"
) -> ExtractionCandidate:
    return ExtractionCandidate(
        posting_id=1,
        external_id=external_id,
        title=title,
        location=None,
        raw_payload={"description": "Build power-market software."},
        employer=Employer(id=1, vertical="grid_power_software", name="Co", ats_type=ats),
    )


def test_fields_to_columns_maps_enums_to_values() -> None:
    cols = fields_to_columns(_FIELDS)
    assert cols["level"] == "new_grad"  # enum → .value
    assert cols["remote"] == "hybrid"
    assert cols["stack"] == ["Python", "AWS"]
    assert cols["comp_min"] == 90000
    assert cols["posted_at"] == "2026-06-18"
    assert "extracted_at" not in cols  # stamped by save_extraction, not here


def test_extract_posting_returns_fields_and_cost() -> None:
    client = cast("Anthropic", _FakeClient())
    fields, cost = extract_posting(client, "some posting text")
    assert fields is _FIELDS
    # 1000 input × $1/MTok + 150 output × $5/MTok = 0.001 + 0.00075
    assert cost == pytest.approx(0.00175)


def test_extract_posting_raises_on_no_parsed_output() -> None:
    client = cast("Anthropic", _FakeClient(parsed=None))
    with pytest.raises(ValueError, match="no parsed output"):
        extract_posting(client, "text")


def test_source_text_uses_raw_payload_for_non_workday() -> None:
    calls: list[tuple[str, str]] = []

    def resolver(employer: Employer, external_path: str) -> dict[str, Any]:
        calls.append((employer.name, external_path))
        return {"jobDescription": "should not be used"}

    text = _source_text(_candidate(AtsType.GREENHOUSE), resolver)
    assert "Build power-market software" in text  # from raw_payload
    assert calls == []  # detail resolver NOT called for non-Workday


def test_source_text_fetches_detail_for_workday() -> None:
    calls: list[tuple[str, str]] = []

    def resolver(employer: Employer, external_path: str) -> dict[str, Any]:
        calls.append((employer.name, external_path))
        return {"jobDescription": "Senior power trader, Houston.", "startDate": "2026-06-01"}

    text = _source_text(_candidate(AtsType.WORKDAY, external_id="/job/X"), resolver)
    assert calls == [("Co", "/job/X")]  # detail fetched lazily with the externalPath
    assert "Senior power trader" in text
