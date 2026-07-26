"""Offline contract tests for the generic BambooHR careers fetcher."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers.bamboohr import BambooHRFetcher
from vja.fetchers.base import FetchError
from vja.models import AtsType, Employer

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_LIST: dict[str, Any] = json.loads((_FIXTURES / "bamboohr_list.json").read_text())
_DETAIL: dict[str, Any] = json.loads((_FIXTURES / "bamboohr_detail.json").read_text())
_LIST_URL = "https://example.bamboohr.com/careers/list"


def _employer() -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="Example Energy",
        ats_type=AtsType.BAMBOOHR,
        ats_slug="example",
    )


@respx.mock
def test_real_fixture_maps_complete_list_without_descriptions() -> None:
    route = respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=_LIST))

    postings = BambooHRFetcher().fetch(_employer())

    assert route.call_count == 1
    assert len(postings) == 2
    first = postings[0]
    assert first.external_id == "125"
    assert first.title == "Business Development Manager"
    assert first.apply_url == "https://example.bamboohr.com/careers/125"
    assert first.location == "Austin, Texas, United States"
    assert first.updated_at is None
    assert first.description is None
    assert first.raw["departmentLabel"] == "Sales US"
    assert postings[1].location == "Dublin, Leinster, Ireland"


@respx.mock
def test_valid_empty_board_is_authoritative_zero_openings() -> None:
    respx.get(_LIST_URL).mock(
        return_value=httpx.Response(200, json={"meta": {"totalCount": 0}, "result": []})
    )
    assert BambooHRFetcher().fetch(_employer()) == []


@pytest.mark.parametrize(
    "job, expected",
    [
        (
            {
                "id": "1",
                "jobOpeningName": "Legacy location",
                "location": {"city": "Denver", "state": "Colorado"},
            },
            "Denver, Colorado",
        ),
        (
            {"id": "2", "jobOpeningName": "Remote role", "location": {}, "isRemote": True},
            "Remote",
        ),
        ({"id": "3", "jobOpeningName": "Unknown location"}, None),
    ],
)
@respx.mock
def test_location_and_remote_fallbacks(job: dict[str, Any], expected: str | None) -> None:
    payload = {"meta": {"totalCount": 1}, "result": [job]}
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    assert BambooHRFetcher().fetch(_employer())[0].location == expected


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "object"),
        ({}, "meta"),
        ({"meta": {}, "result": []}, "totalCount"),
        ({"meta": {"totalCount": 0}}, "result"),
        ({"meta": {"totalCount": 1}, "result": []}, "incomplete"),
        ({"meta": {"totalCount": 0}, "result": {}}, "result"),
    ],
)
@respx.mock
def test_malformed_list_response_fails_closed(payload: Any, message: str) -> None:
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(FetchError, match=message):
        BambooHRFetcher().fetch(_employer())


@pytest.mark.parametrize(
    "job, message",
    [
        ({"jobOpeningName": "No id"}, "id"),
        ({"id": "125"}, "jobOpeningName"),
        ({"id": " ", "jobOpeningName": "Engineer"}, "empty required field"),
        ({"id": "125", "jobOpeningName": "  "}, "empty required field"),
        ("not an object", "not an object"),
    ],
)
@respx.mock
def test_bad_job_fails_entire_list(job: Any, message: str) -> None:
    payload = {"meta": {"totalCount": 1}, "result": [job]}
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(FetchError, match=message):
        BambooHRFetcher().fetch(_employer())


@respx.mock
def test_duplicate_job_ids_fail_entire_list() -> None:
    job = {"id": "125", "jobOpeningName": "Engineer"}
    payload = {"meta": {"totalCount": 2}, "result": [job, job]}
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(FetchError, match="duplicate job ids"):
        BambooHRFetcher().fetch(_employer())


@respx.mock
def test_http_and_non_json_fail_loudly() -> None:
    route = respx.get(_LIST_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError, match="list fetch failed"):
        BambooHRFetcher().fetch(_employer())
    route.mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(FetchError, match="non-JSON"):
        BambooHRFetcher().fetch(_employer())


@respx.mock
def test_detail_returns_only_job_opening_not_application_fields() -> None:
    route = respx.get("https://example.bamboohr.com/careers/125/detail").mock(
        return_value=httpx.Response(200, json=_DETAIL)
    )

    detail = BambooHRFetcher().fetch_detail(_employer(), "125")

    assert detail["description"] == "<p>Build flexible energy products for customers.</p>"
    assert "formFields" not in detail
    assert route.call_count == 1


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "result"),
        ({"result": []}, "result"),
        ({"result": {}}, "jobOpening"),
        ({"result": {"jobOpening": []}}, "jobOpening"),
        ({"result": {"jobOpening": {"description": ""}}}, "description"),
    ],
)
@respx.mock
def test_malformed_detail_fails_loudly(payload: Any, message: str) -> None:
    respx.get("https://example.bamboohr.com/careers/125/detail").mock(
        return_value=httpx.Response(200, json=payload)
    )
    with pytest.raises(FetchError, match=message):
        BambooHRFetcher().fetch_detail(_employer(), "125")


@respx.mock
def test_detail_http_and_non_json_fail_loudly() -> None:
    route = respx.get("https://example.bamboohr.com/careers/125/detail").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(FetchError, match="detail fetch failed"):
        BambooHRFetcher().fetch_detail(_employer(), "125")
    route.mock(return_value=httpx.Response(200, text="not json"))
    with pytest.raises(FetchError, match="non-JSON"):
        BambooHRFetcher().fetch_detail(_employer(), "125")


def test_detail_description_reads_the_job_opening_body() -> None:
    job = _DETAIL["result"]["jobOpening"]
    body = BambooHRFetcher().detail_description(job)

    assert body is not None
    assert body == job["description"].strip()


def test_detail_description_is_none_without_a_body() -> None:
    assert BambooHRFetcher().detail_description({"id": "1"}) is None
