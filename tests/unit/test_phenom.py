"""Offline contract tests for the generic Phenom Career Connect fetcher (D-076)."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers import phenom
from vja.fetchers.base import FetchError
from vja.fetchers.phenom import PhenomFetcher
from vja.models import AtsType, Employer

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_LIST: dict[str, Any] = json.loads((_FIXTURES / "phenom_list.json").read_text())
_DETAIL: dict[str, Any] = json.loads((_FIXTURES / "phenom_detail.json").read_text())
_ENDPOINT = "https://careers.test.com?lang=en_us&country=us"
_WIDGET_URL = "https://careers.test.com/widgets"


def _employer(endpoint: str | None = _ENDPOINT) -> Employer:
    return Employer(
        id=1,
        vertical="aviation_software",
        name="Test Airline",
        ats_type=AtsType.PHENOM,
        endpoint=endpoint,
        careers_url="https://careers.test.com/",
    )


def _job(i: int) -> dict[str, Any]:
    return {
        "jobId": f"JOB{i}",
        "jobSeqNo": f"TENANTJOB{i}EXTERNAL",
        "title": f"Engineer {i}",
        "applyUrl": f"https://ats.test/jobs/{i}",
        "location": "Chicago, Illinois, United States",
        "postedDate": "2026-07-10T12:00:00.000+0000",
    }


def _page(jobs: list[dict[str, Any]], total: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "refineSearch": {
                "status": 200,
                "hits": len(jobs),
                "totalHits": total,
                "data": {"jobs": jobs},
            }
        },
    )


@respx.mock
def test_real_fixture_maps_jobs_and_tenant_config() -> None:
    fixture = dict(_LIST)
    fixture["refineSearch"] = dict(fixture["refineSearch"], totalHits=2)
    route = respx.post(_WIDGET_URL).mock(return_value=httpx.Response(200, json=fixture))

    postings = PhenomFetcher().fetch(_employer())

    assert len(postings) == 2
    first = postings[0]
    assert first.external_id == "ORD00003607"
    assert first.title == "Supervisor - Catering Operations & Logistics"
    assert first.apply_url.endswith("job=ORD00003607")
    assert first.location == "Chicago, Illinois, United States"
    assert first.updated_at == "2026-07-09T21:39:30.000+0000"
    assert first.description is None
    request = route.calls[0].request
    body = json.loads(request.content)
    assert body["lang"] == "en_us" and body["country"] == "us"
    assert body["ddoKey"] == "refineSearch"


@respx.mock
def test_pagination_assembles_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(phenom, "_PAGE_SIZE", 2)
    jobs = [_job(i) for i in range(5)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        offset = body["from"]
        return _page(jobs[offset : offset + 2], total=5)

    route = respx.post(_WIDGET_URL).mock(side_effect=by_offset)
    postings = PhenomFetcher().fetch(_employer())

    assert [posting.external_id for posting in postings] == [f"JOB{i}" for i in range(5)]
    assert route.call_count == 3


@respx.mock
def test_empty_board_returns_empty_list() -> None:
    respx.post(_WIDGET_URL).mock(return_value=_page([], total=0))
    assert PhenomFetcher().fetch(_employer()) == []


@respx.mock
def test_incomplete_fetch_raises_not_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(phenom, "_PAGE_SIZE", 2)
    jobs = [_job(i) for i in range(3)]

    def truncated(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["from"]
        return _page(jobs[offset : offset + 2], total=5)

    respx.post(_WIDGET_URL).mock(side_effect=truncated)
    with pytest.raises(FetchError, match="incomplete"):
        PhenomFetcher().fetch(_employer())


@respx.mock
def test_total_change_midfetch_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(phenom, "_PAGE_SIZE", 1)
    calls = 0

    def changing_total(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _page([_job(calls)], total=2 if calls == 1 else 3)

    respx.post(_WIDGET_URL).mock(side_effect=changing_total)
    with pytest.raises(FetchError, match="total changed"):
        PhenomFetcher().fetch(_employer())


@respx.mock
def test_duplicate_job_ids_fail_loudly() -> None:
    respx.post(_WIDGET_URL).mock(return_value=_page([_job(1), _job(1)], total=2))
    with pytest.raises(FetchError, match="duplicate job ids"):
        PhenomFetcher().fetch(_employer())


@pytest.mark.parametrize(
    "endpoint, message",
    [
        ("https://careers.test.com?country=us", "lang"),
        ("https://careers.test.com?lang=en_us", "country"),
        ("not-a-url?lang=en_us&country=us", "invalid endpoint"),
    ],
)
def test_requires_explicit_tenant_query_config(endpoint: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        PhenomFetcher().fetch(_employer(endpoint))


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "refineSearch"),
        ({"refineSearch": {"status": 500}}, "refineSearch"),
        ({"refineSearch": {"status": 200, "totalHits": "2", "data": {"jobs": []}}}, "totalHits"),
        ({"refineSearch": {"status": 200, "totalHits": 1, "data": {}}}, "jobs list"),
    ],
)
@respx.mock
def test_malformed_list_response_fails_loudly(payload: dict[str, Any], message: str) -> None:
    respx.post(_WIDGET_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(FetchError, match=message):
        PhenomFetcher().fetch(_employer())


@respx.mock
def test_http_and_non_json_fail_loudly() -> None:
    route = respx.post(_WIDGET_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError, match="list fetch failed"):
        PhenomFetcher().fetch(_employer())
    route.mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(FetchError, match="non-JSON"):
        PhenomFetcher().fetch(_employer())


@respx.mock
def test_fetch_detail_uses_stable_job_id_and_returns_full_job() -> None:
    route = respx.post(_WIDGET_URL).mock(return_value=httpx.Response(200, json=_DETAIL))

    detail = PhenomFetcher().fetch_detail(_employer(), "ORD00003607")

    assert "Lead a dynamic team" in detail["description"]
    body = json.loads(route.calls[0].request.content)
    assert body["ddoKey"] == "jobDetail"
    assert body["jobSeqNo"] == "ORD00003607"


@respx.mock
def test_detail_without_description_fails_loudly() -> None:
    payload = {"jobDetail": {"status": 200, "data": {"job": {"title": "No body"}}}}
    respx.post(_WIDGET_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(FetchError, match="description"):
        PhenomFetcher().fetch_detail(_employer(), "JOB1")


@respx.mock
def test_job_missing_required_field_fails_loudly() -> None:
    respx.post(_WIDGET_URL).mock(return_value=_page([{"title": "No id"}], total=1))
    with pytest.raises(FetchError, match="jobId"):
        PhenomFetcher().fetch(_employer())


def test_detail_description_reads_the_job_body() -> None:
    job = _DETAIL["jobDetail"]["data"]["job"]
    assert PhenomFetcher().detail_description(job) == job["description"].strip()


def test_detail_description_is_none_without_a_body() -> None:
    assert PhenomFetcher().detail_description({"jobId": "1"}) is None
