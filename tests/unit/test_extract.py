"""Unit tests for LLM extraction (P5.2) — fully offline (the LLM boundary is faked).

Pins the pure pieces: field→column mapping, cost math from token usage, the Workday-vs-other
source selection, and the no-parsed-output failure path. The live model runs only in the eval.
"""

from typing import Any, cast

import pytest

from vja.db.postings import ExtractionCandidate
from vja.extract import (
    ExtractedFields,
    _posting_source,
    extract_posting,
    fields_to_columns,
)
from vja.llm import StructuredLLM, StructuredResult
from vja.models import AtsType, Employer, Level, RemoteType, TokenUsage

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


class _FakeClient:
    def __init__(self, parsed: ExtractedFields | None) -> None:
        self._parsed = parsed
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> StructuredResult[ExtractedFields]:
        self.calls.append(kwargs)
        if self._parsed is None:
            raise ValueError("LLM returned no structured content")
        return StructuredResult(
            value=self._parsed,
            usage=TokenUsage(input=1000, output=150),
            cost_usd=0.00175,
            model="claude-haiku-4-5",
            latency_seconds=0.25,
            request_id="req-extract",
        )


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


def test_extract_posting_returns_fields_and_real_token_usage() -> None:
    call = extract_posting(cast("StructuredLLM", _FakeClient(_FIELDS)), "some posting text")
    assert call.value is _FIELDS
    assert (call.usage.input, call.usage.output) == (1000, 150)  # real normalized usage
    assert call.cost_usd == pytest.approx(0.00175)  # catalog cost crosses the boundary unchanged


def test_extract_system_prompt_carries_cache_control() -> None:
    client = _FakeClient(_FIELDS)
    extract_posting(cast("StructuredLLM", client), "some posting text")
    call = client.calls[0]
    assert call["model"] == "anthropic/claude-haiku-4-5"
    assert call["cache_system"] is True  # stable instruction prefix (D-069)
    assert "You extract structured fields" in call["system"]


def test_extract_posting_model_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VJA_EXTRACT_MODEL", "deepseek/test-extract")
    client = _FakeClient(_FIELDS)
    extract_posting(cast("StructuredLLM", client), "some posting text")
    assert client.calls[0]["model"] == "deepseek/test-extract"


def test_extract_posting_raises_on_no_parsed_output() -> None:
    client = _FakeClient(parsed=None)
    with pytest.raises(ValueError, match="no structured content"):
        extract_posting(cast("StructuredLLM", client), "text")


def test_source_text_uses_raw_payload_for_rich_list_ats() -> None:
    calls: list[tuple[str, str]] = []

    def resolver(employer: Employer, external_path: str) -> dict[str, Any]:
        calls.append((employer.name, external_path))
        return {"jobDescription": "should not be used"}

    source = _posting_source(_candidate(AtsType.GREENHOUSE), resolver)
    assert "Build power-market software" in source.text  # from raw_payload
    assert calls == []  # detail resolver NOT called for a rich-list ATS
    # A rich-list body was already stored at insert, so extraction offers nothing (D-095).
    assert source.description is None


def test_source_text_fetches_detail_for_workday() -> None:
    calls: list[tuple[str, str]] = []

    def resolver(employer: Employer, external_path: str) -> dict[str, Any]:
        calls.append((employer.name, external_path))
        return {"jobDescription": "Senior power trader, Houston.", "startDate": "2026-06-01"}

    source = _posting_source(_candidate(AtsType.WORKDAY, external_id="/job/X"), resolver)
    assert calls == [("Co", "/job/X")]  # detail fetched lazily with the externalPath
    assert "Senior power trader" in source.text
    # The one fetch feeds both the model and the stored body — never a second request (D-095).
    assert source.description == "Senior power trader, Houston."


@pytest.mark.parametrize(
    "ats",
    [
        AtsType.SMARTRECRUITERS,
        AtsType.ORACLE_HCM,
        AtsType.RADANCY,
        AtsType.PAYLOCITY,
        AtsType.PHENOM,
        AtsType.BAMBOOHR,
    ],
)
def test_source_text_fetches_detail_for_list_only_ats(ats: AtsType) -> None:
    # The list-only Tier-B/C ATSs (D-050/D-051/D-052) route to their lazy detail like Workday.
    calls: list[tuple[str, str]] = []

    def resolver(employer: Employer, external_id: str) -> dict[str, Any]:
        calls.append((employer.name, external_id))
        return {"body": "Grid software engineer, Atlanta."}

    source = _posting_source(_candidate(ats, external_id="42"), resolver)
    assert calls == [("Co", "42")]  # detail fetched lazily
    assert "Grid software engineer" in source.text
