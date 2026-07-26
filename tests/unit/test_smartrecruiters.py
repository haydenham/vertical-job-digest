"""Unit tests for the SmartRecruiters fetcher.

Mapping is asserted against a captured real Vitol response (`tests/fixtures/smartrecruiters.json`,
D-019); HTTP stubbed by respx. SmartRecruiters mirrors Workday's contract: list-only (no description
or apply URL in the list) + paginate-or-fail + a lazy `fetch_detail`. The apply URL is *constructed*
from the slug + posting id; the description comes only from the per-posting detail endpoint.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers import smartrecruiters
from vja.fetchers.base import FetchError
from vja.fetchers.smartrecruiters import SmartRecruitersFetcher
from vja.models import AtsType, Employer

_FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "smartrecruiters.json").read_text()
)
_CONTENT: list[dict[str, Any]] = _FIXTURE["content"]
_DETAIL: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "smartrecruiters_detail.json").read_text()
)
# Derived from the slug (`endpoints.py`) — the API host is uniform across tenants.
_ENDPOINT = "https://api.smartrecruiters.com/v1/companies/Vitol/postings"


def _employer() -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="Vitol",
        ats_type=AtsType.SMARTRECRUITERS,
        ats_slug="Vitol",
    )


def _job(i: int) -> dict[str, Any]:
    return {
        "id": f"74400{i}",
        "name": f"Engineer {i}",
        "location": {
            "city": "Houston",
            "region": "TX",
            "fullLocation": "Houston, TX, United States",
        },
        "releasedDate": "2026-06-23T17:40:25.923Z",
    }


def _page(content: list[dict[str, Any]], total: int) -> httpx.Response:
    return httpx.Response(
        200, json={"offset": 0, "limit": 100, "totalFound": total, "content": content}
    )


@respx.mock
def test_maps_fixture_jobs() -> None:
    route = respx.get(_ENDPOINT).mock(return_value=_page(_CONTENT, total=len(_CONTENT)))

    postings = SmartRecruitersFetcher().fetch(_employer())

    assert route.called
    assert len(postings) == len(_CONTENT)
    job0, first = _CONTENT[0], postings[0]
    assert first.external_id == str(job0["id"])  # the diff key (D-016)
    assert first.title == job0["name"]
    # apply_url is constructed from slug + id (the list carries no apply URL).
    assert first.apply_url == f"https://jobs.smartrecruiters.com/Vitol/{job0['id']}"
    assert first.updated_at == job0["releasedDate"]  # real ISO date (freshness, D-030)
    assert first.description is None  # list-only; description is a lazy detail fetch
    assert first.raw == job0


@respx.mock
def test_location_collapses_empty_segments() -> None:
    # The fixture's first posting is "Singapore, , Singapore" — the empty region segment drops.
    respx.get(_ENDPOINT).mock(return_value=_page([_CONTENT[0]], total=1))
    assert SmartRecruitersFetcher().fetch(_employer())[0].location == "Singapore, Singapore"


@respx.mock
def test_location_keeps_full_us_string() -> None:
    respx.get(_ENDPOINT).mock(return_value=_page([_job(0)], total=1))
    assert SmartRecruitersFetcher().fetch(_employer())[0].location == "Houston, TX, United States"


@respx.mock
def test_pagination_assembles_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smartrecruiters, "_PAGE_SIZE", 2)
    jobs = [_job(i) for i in range(5)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        return _page(jobs[offset : offset + 2], total=5)

    route = respx.get(_ENDPOINT).mock(side_effect=by_offset)

    postings = SmartRecruitersFetcher().fetch(_employer())

    assert [p.external_id for p in postings] == [j["id"] for j in jobs]
    assert route.call_count == 3  # offsets 0, 2, 4


@respx.mock
def test_incomplete_fetch_raises_not_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    # totalFound says 5 but the board only yields 3, then an empty page → truncated, must fail.
    monkeypatch.setattr(smartrecruiters, "_PAGE_SIZE", 2)
    jobs = [_job(i) for i in range(3)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        return _page(jobs[offset : offset + 2], total=5)

    respx.get(_ENDPOINT).mock(side_effect=by_offset)

    with pytest.raises(FetchError, match="incomplete"):
        SmartRecruitersFetcher().fetch(_employer())


@respx.mock
def test_overcount_fetch_raises_not_partial() -> None:
    respx.get(_ENDPOINT).mock(return_value=_page([_job(0), _job(1)], total=1))

    with pytest.raises(FetchError, match="incomplete"):
        SmartRecruitersFetcher().fetch(_employer())


@respx.mock
def test_total_change_midfetch_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smartrecruiters, "_PAGE_SIZE", 2)
    jobs = [_job(i) for i in range(5)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        return _page(jobs[offset : offset + 2], total=5 if offset == 0 else 6)

    respx.get(_ENDPOINT).mock(side_effect=by_offset)

    with pytest.raises(FetchError, match="total changed"):
        SmartRecruitersFetcher().fetch(_employer())


@respx.mock
def test_midpagination_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smartrecruiters, "_PAGE_SIZE", 2)
    jobs = [_job(i) for i in range(5)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        if offset == 2:
            raise httpx.ConnectError("boom")
        return _page(jobs[offset : offset + 2], total=5)

    respx.get(_ENDPOINT).mock(side_effect=by_offset)

    with pytest.raises(FetchError):
        SmartRecruitersFetcher().fetch(_employer())


@respx.mock
def test_empty_board_returns_empty_list() -> None:
    respx.get(_ENDPOINT).mock(return_value=_page([], total=0))
    assert SmartRecruitersFetcher().fetch(_employer()) == []


@respx.mock
def test_missing_release_date_yields_none() -> None:
    job = _job(0)
    del job["releasedDate"]
    respx.get(_ENDPOINT).mock(return_value=_page([job], total=1))
    assert SmartRecruitersFetcher().fetch(_employer())[0].updated_at is None


@respx.mock
def test_missing_location_yields_none() -> None:
    job = _job(0)
    del job["location"]
    respx.get(_ENDPOINT).mock(return_value=_page([job], total=1))
    assert SmartRecruitersFetcher().fetch(_employer())[0].location is None


@respx.mock
def test_http_500_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError):
        SmartRecruitersFetcher().fetch(_employer())


@respx.mock
def test_non_json_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(FetchError):
        SmartRecruitersFetcher().fetch(_employer())


@respx.mock
def test_missing_content_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, json={"totalFound": 0}))
    with pytest.raises(FetchError, match="content"):
        SmartRecruitersFetcher().fetch(_employer())


@respx.mock
def test_missing_totalfound_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, json={"content": [_job(0)]}))
    with pytest.raises(FetchError, match="totalFound"):
        SmartRecruitersFetcher().fetch(_employer())


@respx.mock
def test_job_missing_id_raises_fetcherror() -> None:
    bad = {"name": "No id"}
    respx.get(_ENDPOINT).mock(return_value=_page([bad], total=1))
    with pytest.raises(FetchError, match="id"):
        SmartRecruitersFetcher().fetch(_employer())


@respx.mock
def test_job_missing_name_raises_fetcherror() -> None:
    bad = {"id": "123"}
    respx.get(_ENDPOINT).mock(return_value=_page([bad], total=1))
    with pytest.raises(FetchError, match="name"):
        SmartRecruitersFetcher().fetch(_employer())


@respx.mock
def test_fetch_detail_returns_full_posting() -> None:
    eid = "744000133666057"
    route = respx.get(f"{_ENDPOINT}/{eid}").mock(return_value=httpx.Response(200, json=_DETAIL))

    detail = SmartRecruitersFetcher().fetch_detail(_employer(), eid)

    assert route.called
    assert "jobDescription" in detail["jobAd"]["sections"]  # the Layer-2 body


@respx.mock
def test_fetch_detail_http_error_raises() -> None:
    respx.get(f"{_ENDPOINT}/x").mock(return_value=httpx.Response(404))
    with pytest.raises(FetchError):
        SmartRecruitersFetcher().fetch_detail(_employer(), "x")


@respx.mock
def test_fetch_detail_non_json_raises() -> None:
    respx.get(f"{_ENDPOINT}/x").mock(return_value=httpx.Response(200, text="nope"))
    with pytest.raises(FetchError):
        SmartRecruitersFetcher().fetch_detail(_employer(), "x")


def test_detail_description_joins_the_job_ad_sections() -> None:
    # The body lives split across titled `jobAd.sections`; extraction keeps it (D-095) instead of
    # discarding the detail it already fetched.
    body = SmartRecruitersFetcher().detail_description(_DETAIL)

    assert body is not None
    assert "Vitol is a leader in the energy sector" in body  # companyDescription
    assert body.count("\n\n") >= 2  # several sections, each its own block


def test_detail_description_is_none_without_sections() -> None:
    assert SmartRecruitersFetcher().detail_description({"jobAd": {}}) is None
