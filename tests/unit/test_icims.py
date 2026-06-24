"""Unit tests for the iCIMS (Jibe Career Sites) fetcher.

Mapping is asserted against a captured real Garmin response (`tests/fixtures/icims.json`,
D-019); HTTP stubbed by respx. The iCIMS-specific contracts mirror Workday: full pagination
assembles every page; a truncated/short fetch raises `FetchError` (never a partial list → no
false closures); transport/parse/shape failures raise `FetchError`. Unlike Workday the payload
is rich, so `apply_url`, `description`, and `updated_at` are populated from the list itself.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers import icims
from vja.fetchers.base import FetchError
from vja.fetchers.icims import IcimsFetcher
from vja.models import AtsType, Employer

_FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "icims.json").read_text()
)
_JOBS: list[dict[str, Any]] = _FIXTURE["jobs"]
_ENDPOINT = "https://careers.garmin.com/api/jobs"


def _employer(endpoint: str = _ENDPOINT) -> Employer:
    return Employer(
        id=1,
        vertical="aviation_software",
        name="Garmin",
        ats_type=AtsType.ICIMS,
        ats_slug="garmin",
        endpoint=endpoint,
    )


def _job(i: int) -> dict[str, Any]:
    return {
        "data": {
            "req_id": str(i),
            "slug": str(i),
            "title": f"Engineer {i}",
            "apply_url": f"https://careers-x.icims.com/jobs/{i}/login",
            "full_location": "Remote, US",
            "update_date": "2026-06-24T00:00:00+0000",
            "description": f"Overview {i}",
            "responsibilities": f"Do {i}",
            "qualifications": f"Need {i}",
        }
    }


def _page(jobs: list[dict[str, Any]], total: int) -> httpx.Response:
    return httpx.Response(200, json={"jobs": jobs, "totalCount": total})


@respx.mock
def test_maps_fixture_jobs() -> None:
    route = respx.get(_ENDPOINT).mock(return_value=_page(_JOBS, total=len(_JOBS)))

    postings = IcimsFetcher().fetch(_employer())

    assert route.called
    assert len(postings) == len(_JOBS)
    data0, first = _JOBS[0]["data"], postings[0]
    assert first.external_id == str(data0["req_id"])  # the diff key (D-016)
    assert first.title == data0["title"]
    assert first.apply_url == data0["apply_url"]  # given directly by the Jibe payload
    assert first.location == data0["full_location"]
    assert first.updated_at == data0["update_date"]  # real ISO date (freshness win vs Workday)
    # description joins overview + responsibilities + qualifications for Layer 2.
    assert data0["responsibilities"] in (first.description or "")
    assert data0["qualifications"] in (first.description or "")
    assert first.raw == data0


@respx.mock
def test_pagination_assembles_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(icims, "_PAGE_SIZE", 2)
    jobs = [_job(i) for i in range(5)]

    def by_page(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        start = (page - 1) * 2
        return _page(jobs[start : start + 2], total=5)

    route = respx.get(_ENDPOINT).mock(side_effect=by_page)

    postings = IcimsFetcher().fetch(_employer())

    assert [p.external_id for p in postings] == [j["data"]["req_id"] for j in jobs]
    assert route.call_count == 3  # pages 1, 2, 3


@respx.mock
def test_incomplete_fetch_raises_not_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    # totalCount says 5 but the board only yields 3, then an empty page → truncated, must fail.
    monkeypatch.setattr(icims, "_PAGE_SIZE", 2)
    jobs = [_job(i) for i in range(3)]

    def by_page(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        start = (page - 1) * 2
        return _page(jobs[start : start + 2], total=5)

    respx.get(_ENDPOINT).mock(side_effect=by_page)

    with pytest.raises(FetchError, match="incomplete"):
        IcimsFetcher().fetch(_employer())


@respx.mock
def test_midpagination_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(icims, "_PAGE_SIZE", 2)
    jobs = [_job(i) for i in range(5)]

    def by_page(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if page == 2:
            raise httpx.ConnectError("boom")
        start = (page - 1) * 2
        return _page(jobs[start : start + 2], total=5)

    respx.get(_ENDPOINT).mock(side_effect=by_page)

    with pytest.raises(FetchError):
        IcimsFetcher().fetch(_employer())


@respx.mock
def test_empty_board_returns_empty_list() -> None:
    respx.get(_ENDPOINT).mock(return_value=_page([], total=0))
    assert IcimsFetcher().fetch(_employer()) == []


@respx.mock
def test_http_500_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError):
        IcimsFetcher().fetch(_employer())


@respx.mock
def test_non_json_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(FetchError):
        IcimsFetcher().fetch(_employer())


@respx.mock
def test_missing_jobs_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, json={"totalCount": 0}))
    with pytest.raises(FetchError, match="jobs"):
        IcimsFetcher().fetch(_employer())


@respx.mock
def test_missing_totalcount_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": [_job(0)]}))
    with pytest.raises(FetchError, match="totalCount"):
        IcimsFetcher().fetch(_employer())


@respx.mock
def test_job_missing_reqid_raises_fetcherror() -> None:
    bad = {"data": {"title": "No id", "apply_url": "https://x/jobs/1/login"}}
    respx.get(_ENDPOINT).mock(return_value=_page([bad], total=1))
    with pytest.raises(FetchError, match="req_id"):
        IcimsFetcher().fetch(_employer())


@respx.mock
def test_job_missing_data_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=_page([{"no_data": True}], total=1))
    with pytest.raises(FetchError, match="data"):
        IcimsFetcher().fetch(_employer())
