"""Offline contract tests for the generic Pinpoint postings fetcher."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers.base import FetchError
from vja.fetchers.pinpoint import PinpointFetcher
from vja.models import AtsType, Employer

_FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "pinpoint_postings.json").read_text()
)
_URL = "https://example.pinpointhq.com/postings.json"


def _employer(*, endpoint: str | None = None) -> Employer:
    return Employer(
        id=1,
        vertical="aviation_software",
        name="Example Aviation",
        ats_type=AtsType.PINPOINT,
        ats_slug="example",
        endpoint=endpoint,
    )


@respx.mock
def test_real_fixture_maps_complete_rich_list() -> None:
    route = respx.get(_URL).mock(return_value=httpx.Response(200, json=_FIXTURE))

    postings = PinpointFetcher().fetch(_employer())

    assert route.call_count == 1
    assert len(postings) == 2
    first = postings[0]
    assert first.external_id == "490307"
    assert first.external_id != first.raw["job"]["id"]
    assert first.title == "Software Engineer I"
    assert first.apply_url == "https://example.pinpointhq.com/en/postings/first-public-id"
    assert first.location == "McLean, Virginia"
    assert first.updated_at is None
    assert first.raw["deadline_at"] == "2026-07-31T23:59:59-04:00"
    assert first.description is not None
    assert "Build aviation data products" in first.description
    assert "Ship reliable Python services" in first.description
    assert "Python and SQL" in first.description
    assert "Medical and retirement" in first.description
    assert '"compensation_minimum": 85000' in first.description
    assert postings[1].external_id == "495358"
    assert postings[1].location == "United States"


@respx.mock
def test_explicit_custom_domain_endpoint_is_authoritative() -> None:
    endpoint = "https://careers.example.com/postings.json"
    route = respx.get(endpoint).mock(return_value=httpx.Response(200, json={"data": []}))
    assert PinpointFetcher().fetch(_employer(endpoint=endpoint)) == []
    assert route.call_count == 1


@respx.mock
def test_valid_empty_board_is_authoritative_zero_openings() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"data": []}))
    assert PinpointFetcher().fetch(_employer()) == []


@pytest.mark.parametrize(
    "payload",
    [[], {}, {"data": {}}, {"data": ["not an object"]}],
)
@respx.mock
def test_malformed_list_response_fails_closed(payload: Any) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(FetchError):
        PinpointFetcher().fetch(_employer())


@pytest.mark.parametrize(
    "posting, field",
    [
        ({"title": "Engineer", "url": "https://example.test/job"}, "id"),
        ({"id": "1", "url": "https://example.test/job"}, "title"),
        ({"id": "1", "title": "Engineer"}, "url"),
    ],
)
@respx.mock
def test_missing_required_fields_fail_entire_list(posting: dict[str, Any], field: str) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"data": [posting]}))
    with pytest.raises(FetchError, match=field):
        PinpointFetcher().fetch(_employer())


@pytest.mark.parametrize(
    "posting",
    [
        {"id": " ", "title": "Engineer", "url": "https://example.test/job"},
        {"id": "1", "title": " ", "url": "https://example.test/job"},
        {"id": "1", "title": "Engineer", "url": " "},
        {"id": True, "title": "Engineer", "url": "https://example.test/job"},
    ],
)
@respx.mock
def test_empty_or_invalid_required_fields_fail_entire_list(posting: dict[str, Any]) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"data": [posting]}))
    with pytest.raises(FetchError, match="empty required field"):
        PinpointFetcher().fetch(_employer())


@respx.mock
def test_duplicate_posting_ids_fail_entire_list() -> None:
    posting = {"id": "1", "title": "Engineer", "url": "https://example.test/job"}
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"data": [posting, posting]}))
    with pytest.raises(FetchError, match="duplicate posting ids"):
        PinpointFetcher().fetch(_employer())


@respx.mock
def test_optional_location_and_content_can_be_absent() -> None:
    posting = {"id": "1", "title": "Engineer", "url": "https://example.test/job"}
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"data": [posting]}))
    result = PinpointFetcher().fetch(_employer())[0]
    assert result.location is None
    assert result.description is None


@respx.mock
def test_http_and_non_json_fail_loudly() -> None:
    route = respx.get(_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(FetchError, match="fetch failed"):
        PinpointFetcher().fetch(_employer())
    route.mock(return_value=httpx.Response(200, text="not json"))
    with pytest.raises(FetchError, match="non-JSON"):
        PinpointFetcher().fetch(_employer())
