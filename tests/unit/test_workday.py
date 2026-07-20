"""Unit tests for the Workday cxs fetcher (P4B1).

Mapping is asserted against a captured real PJM response (`tests/fixtures/workday_pjm_jobs.json`,
D-019); HTTP stubbed by respx. The Workday-specific contracts: full pagination assembles every
page; a truncated/short fetch raises `FetchError` (never a partial list → no false closures);
transport/parse/shape failures raise `FetchError`; the apply URL is derived from the cxs endpoint.
"""

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers import workday
from vja.fetchers.base import FetchError
from vja.fetchers.workday import WorkdayFetcher
from vja.models import AtsType, Employer

_FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "workday_pjm_jobs.json").read_text()
)
_JOBS: list[dict[str, Any]] = _FIXTURE["jobPostings"]
_ENDPOINT = "https://pjm.wd5.myworkdayjobs.com/wday/cxs/pjm/pjmcareers/jobs"


def _employer(endpoint: str = _ENDPOINT) -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="PJM Interconnection",
        ats_type=AtsType.WORKDAY,
        ats_slug="pjm:wd5:pjmcareers",
        endpoint=endpoint,
    )


def _job(i: int) -> dict[str, Any]:
    return {
        "title": f"Engineer {i}",
        "externalPath": f"/job/Remote/Role_{i}_REQ-{i}",
        "locationsText": "Remote",
        "postedOn": "Posted 1 Day Ago",
        "bulletFields": [f"REQ-{i}"],
    }


def _page(jobs: list[dict[str, Any]], total: int) -> httpx.Response:
    return httpx.Response(200, json={"total": total, "jobPostings": jobs})


def _capture_workday_logs(caplog: pytest.LogCaptureFixture) -> None:
    # Alembic's test-only fileConfig disables loggers imported before migration tests run.
    logging.getLogger("vja.fetchers.workday").disabled = False
    caplog.set_level(logging.INFO, logger="vja.fetchers.workday")


@respx.mock
def test_maps_fixture_jobs() -> None:
    route = respx.post(_ENDPOINT).mock(return_value=_page(_JOBS, total=len(_JOBS)))

    postings = WorkdayFetcher().fetch(_employer())

    assert route.called
    assert len(postings) == len(_JOBS)
    job0, first = _JOBS[0], postings[0]
    assert first.external_id == job0["externalPath"]  # the diff key (D-016)
    assert first.title == job0["title"]
    assert first.location == job0["locationsText"]
    assert first.apply_url == f"https://pjm.wd5.myworkdayjobs.com/pjmcareers{job0['externalPath']}"
    assert first.updated_at is None  # Workday list has only a relative postedOn
    assert first.description is None  # list-only
    assert first.raw == job0


@respx.mock
def test_pagination_assembles_every_page(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(workday, "_PAGE_SIZE", 2)
    _capture_workday_logs(caplog)
    jobs = [_job(i) for i in range(5)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["offset"]
        return _page(jobs[offset : offset + 2], total=5)

    route = respx.post(_ENDPOINT).mock(side_effect=by_offset)

    postings = WorkdayFetcher().fetch(_employer())

    assert [p.external_id for p in postings] == [j["externalPath"] for j in jobs]
    assert route.call_count == 3  # offsets 0, 2, 4
    assert "reported_totals=5,5,5" in caplog.text
    assert "page_sizes=2,2,1" in caplog.text
    assert "would_complete=True diagnostic_only=False" in caplog.text


@respx.mock
def test_incomplete_fetch_raises_not_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    # total says 5 but the board only yields 3, then an empty page → truncated, must fail loudly.
    monkeypatch.setattr(workday, "_PAGE_SIZE", 2)
    jobs = [_job(i) for i in range(3)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["offset"]
        return _page(jobs[offset : offset + 2], total=5)

    respx.post(_ENDPOINT).mock(side_effect=by_offset)

    with pytest.raises(FetchError, match="incomplete"):
        WorkdayFetcher().fetch(_employer())


@respx.mock
def test_overcount_fetch_raises_not_partial() -> None:
    respx.post(_ENDPOINT).mock(return_value=_page([_job(0), _job(1)], total=1))

    with pytest.raises(FetchError, match="incomplete"):
        WorkdayFetcher().fetch(_employer())


@respx.mock
def test_total_change_midfetch_finishes_quarantined_diagnostic_walk(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(workday, "_PAGE_SIZE", 2)
    _capture_workday_logs(caplog)
    jobs = [_job(i) for i in range(5)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["offset"]
        return _page(jobs[offset : offset + 2], total=5 if offset == 0 else 6)

    route = respx.post(_ENDPOINT).mock(side_effect=by_offset)

    with pytest.raises(FetchError, match="total changed"):
        WorkdayFetcher().fetch(_employer())

    assert route.call_count == 3  # the invalid snapshot still walks to page one's target
    assert "action=diagnostic_shadow" in caplog.text
    assert "reported_totals=5,6,6" in caplog.text
    assert "would_complete=True diagnostic_only=True" in caplog.text


@respx.mock
def test_zero_later_totals_capture_complete_disjoint_shadow_walk(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The July-17 production shape: later totals are zero but rows may still be usable."""
    monkeypatch.setattr(workday, "_PAGE_SIZE", 2)
    _capture_workday_logs(caplog)
    jobs = [_job(i) for i in range(5)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["offset"]
        return _page(jobs[offset : offset + 2], total=5 if offset == 0 else 0)

    route = respx.post(_ENDPOINT).mock(side_effect=by_offset)

    with pytest.raises(FetchError, match="5 → 0"):
        WorkdayFetcher().fetch(_employer())

    assert route.call_count == 3
    assert "reported_totals=5,0,0" in caplog.text
    assert "page_sizes=2,2,1" in caplog.text
    assert "collected_rows=5 unique_ids=5 overlap=0" in caplog.text
    assert "would_complete=True diagnostic_only=True" in caplog.text
    assert jobs[0]["externalPath"] not in caplog.text  # identities are fingerprinted, not logged


@respx.mock
def test_shadow_walk_identifies_repeated_pages(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(workday, "_PAGE_SIZE", 2)
    _capture_workday_logs(caplog)
    first_page = [_job(0), _job(1)]

    def repeats_first_page(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["offset"]
        return _page(first_page, total=5 if offset == 0 else 0)

    route = respx.post(_ENDPOINT).mock(side_effect=repeats_first_page)

    with pytest.raises(FetchError, match="5 → 0"):
        WorkdayFetcher().fetch(_employer())

    assert route.call_count == 3
    assert "collected_rows=6 unique_ids=2 overlap=4" in caplog.text
    assert "would_complete=False diagnostic_only=True" in caplog.text


@respx.mock
def test_shadow_walk_identifies_empty_page_before_target(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(workday, "_PAGE_SIZE", 2)
    _capture_workday_logs(caplog)
    first_page = [_job(0), _job(1)]

    def empty_second_page(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["offset"]
        return _page(first_page if offset == 0 else [], total=5 if offset == 0 else 0)

    route = respx.post(_ENDPOINT).mock(side_effect=empty_second_page)

    with pytest.raises(FetchError, match="5 → 0"):
        WorkdayFetcher().fetch(_employer())

    assert route.call_count == 2
    assert "reported_totals=5,0" in caplog.text
    assert "page_sizes=2,0" in caplog.text
    assert "collected_rows=2 unique_ids=2 overlap=0" in caplog.text
    assert "would_complete=False diagnostic_only=True" in caplog.text


@respx.mock
def test_midpagination_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workday, "_PAGE_SIZE", 2)
    jobs = [_job(i) for i in range(5)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["offset"]
        if offset == 2:
            raise httpx.ConnectError("boom")
        return _page(jobs[offset : offset + 2], total=5)

    respx.post(_ENDPOINT).mock(side_effect=by_offset)

    with pytest.raises(FetchError):
        WorkdayFetcher().fetch(_employer())


@respx.mock
def test_empty_board_returns_empty_list() -> None:
    respx.post(_ENDPOINT).mock(return_value=_page([], total=0))
    assert WorkdayFetcher().fetch(_employer()) == []


@respx.mock
def test_http_500_raises_fetcherror() -> None:
    respx.post(_ENDPOINT).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError):
        WorkdayFetcher().fetch(_employer())


@respx.mock
def test_non_json_raises_fetcherror() -> None:
    respx.post(_ENDPOINT).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(FetchError):
        WorkdayFetcher().fetch(_employer())


@respx.mock
def test_missing_jobpostings_raises_fetcherror() -> None:
    respx.post(_ENDPOINT).mock(return_value=httpx.Response(200, json={"total": 0}))
    with pytest.raises(FetchError, match="jobPostings"):
        WorkdayFetcher().fetch(_employer())


@respx.mock
def test_missing_total_raises_fetcherror() -> None:
    respx.post(_ENDPOINT).mock(return_value=httpx.Response(200, json={"jobPostings": [_job(0)]}))
    with pytest.raises(FetchError, match="total"):
        WorkdayFetcher().fetch(_employer())


@respx.mock
def test_job_missing_externalpath_raises_fetcherror() -> None:
    bad = {"title": "No path", "locationsText": "Remote"}
    respx.post(_ENDPOINT).mock(return_value=_page([bad], total=1))
    with pytest.raises(FetchError, match="externalPath"):
        WorkdayFetcher().fetch(_employer())


def test_non_cxs_endpoint_raises_fetcherror() -> None:
    with pytest.raises(FetchError, match="not a cxs URL"):
        WorkdayFetcher().fetch(_employer(endpoint="https://example.com/careers"))
