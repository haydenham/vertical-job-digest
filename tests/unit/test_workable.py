"""Unit tests for the Workable fetcher.

Mapping is asserted against a captured real Vortexa response (`tests/fixtures/workable.json`,
D-019); HTTP stubbed by respx. Workable's contract differs from iCIMS/Workday: the embed-widget
returns *all* open jobs in one response (no pagination), so — like Greenhouse — the false-closure
guard is the single-request contract: a clean 200 is the authoritative complete set, an empty
`jobs` array is a legitimate "0 open", and any transport/parse/shape error raises `FetchError`.
The list is rich (`?details=true`), so `apply_url`, `description`, and `updated_at` come from it.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers.base import FetchError
from vja.fetchers.workable import WorkableFetcher
from vja.models import AtsType, Employer

_FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "workable.json").read_text()
)
_JOBS: list[dict[str, Any]] = _FIXTURE["jobs"]
# Derived from the slug (`endpoints.py`) — the widget host is uniform across tenants.
_ENDPOINT = "https://apply.workable.com/api/v1/widget/accounts/vortexa?details=true"


def _employer() -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="Vortexa",
        ats_type=AtsType.WORKABLE,
        ats_slug="vortexa",
    )


def _job(i: int) -> dict[str, Any]:
    return {
        "shortcode": f"CODE{i}",
        "title": f"Engineer {i}",
        "url": f"https://apply.workable.com/j/CODE{i}",
        "application_url": f"https://apply.workable.com/j/CODE{i}/apply",
        "published_on": "2026-06-23",
        "created_at": "2026-06-20",
        "city": "Houston",
        "state": "Texas",
        "country": "United States",
        "description": f"<p>About role {i}</p>",
    }


def _board(jobs: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"name": "Vortexa", "description": "x", "jobs": jobs})


@respx.mock
def test_maps_fixture_jobs() -> None:
    route = respx.get(_ENDPOINT).mock(return_value=_board(_JOBS))

    postings = WorkableFetcher().fetch(_employer())

    assert route.called
    assert len(postings) == len(_JOBS)
    job0, first = _JOBS[0], postings[0]
    assert first.external_id == str(job0["shortcode"])  # the diff key (D-016)
    assert first.title == job0["title"]
    assert first.apply_url == job0["url"]  # the public posting page
    # location joins city/state/country (full names → Stage-B US signal).
    for part in (job0["city"], job0["state"], job0["country"]):
        assert part in (first.location or "")
    assert first.updated_at == job0["published_on"]  # real ISO date (freshness, D-030)
    assert job0["description"] in (first.description or "")  # rich list, no detail fetch
    assert first.raw == job0


@respx.mock
def test_returns_all_jobs_single_response() -> None:
    jobs = [_job(i) for i in range(5)]
    route = respx.get(_ENDPOINT).mock(return_value=_board(jobs))

    postings = WorkableFetcher().fetch(_employer())

    assert [p.external_id for p in postings] == [j["shortcode"] for j in jobs]
    assert route.call_count == 1  # single request, no pagination


@respx.mock
def test_empty_board_returns_empty_list() -> None:
    # A real "0 open" board (e.g. Energy Aspects at probe) is legitimate, not a failure.
    respx.get(_ENDPOINT).mock(return_value=_board([]))
    assert WorkableFetcher().fetch(_employer()) == []


@respx.mock
def test_falls_back_to_created_at_when_no_published_on() -> None:
    job = _job(0)
    del job["published_on"]
    respx.get(_ENDPOINT).mock(return_value=_board([job]))
    assert WorkableFetcher().fetch(_employer())[0].updated_at == job["created_at"]


@respx.mock
def test_missing_location_fields_yield_none() -> None:
    job = _job(0)
    for f in ("city", "state", "country"):
        del job[f]
    respx.get(_ENDPOINT).mock(return_value=_board([job]))
    assert WorkableFetcher().fetch(_employer())[0].location is None


@respx.mock
def test_http_500_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError):
        WorkableFetcher().fetch(_employer())


@respx.mock
def test_transport_error_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(FetchError):
        WorkableFetcher().fetch(_employer())


@respx.mock
def test_non_json_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(FetchError):
        WorkableFetcher().fetch(_employer())


@respx.mock
def test_missing_jobs_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, json={"name": "Vortexa"}))
    with pytest.raises(FetchError, match="jobs"):
        WorkableFetcher().fetch(_employer())


@respx.mock
def test_job_missing_shortcode_raises_fetcherror() -> None:
    bad = {"title": "No id", "url": "https://apply.workable.com/j/x"}
    respx.get(_ENDPOINT).mock(return_value=_board([bad]))
    with pytest.raises(FetchError, match="shortcode"):
        WorkableFetcher().fetch(_employer())


@respx.mock
def test_job_empty_required_field_raises_fetcherror() -> None:
    bad = {"shortcode": "", "title": "Has title", "url": "https://apply.workable.com/j/x"}
    respx.get(_ENDPOINT).mock(return_value=_board([bad]))
    with pytest.raises(FetchError, match="empty required field"):
        WorkableFetcher().fetch(_employer())
