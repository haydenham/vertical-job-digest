"""Unit tests for the Ashby fetcher (Chunk 5).

Mapping asserted against a captured real response (`tests/fixtures/ashby.json`, D-019)
with HTTP stubbed by respx. Ashby returns ``{"jobs": [...]}``.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers.ashby import AshbyFetcher
from vja.fetchers.base import FetchError
from vja.models import AtsType, Employer

_FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "ashby.json").read_text()
)
_URL = "https://api.ashbyhq.com/posting-api/job-board/weave-grid"


def _employer(slug: str = "weave-grid") -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="WeaveGrid",
        ats_type=AtsType.ASHBY,
        ats_slug=slug,
    )


@respx.mock
def test_fetch_maps_every_fixture_job() -> None:
    route = respx.get(_URL).mock(return_value=httpx.Response(200, json=_FIXTURE))

    postings = AshbyFetcher().fetch(_employer())

    assert route.called
    assert len(postings) == len(_FIXTURE["jobs"])

    job0 = _FIXTURE["jobs"][0]
    first = postings[0]
    assert first.external_id == str(job0["id"])
    assert first.title == job0["title"]
    assert first.apply_url == job0["applyUrl"]
    assert first.location == job0["location"]
    assert first.raw == job0
    assert first.description == job0["descriptionPlain"]


@respx.mock
def test_apply_url_falls_back_to_job_url() -> None:
    job = {"id": "abc", "title": "Engineer", "jobUrl": "https://jobs.ashbyhq.com/x/abc"}
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"jobs": [job]}))
    assert AshbyFetcher().fetch(_employer())[0].apply_url == "https://jobs.ashbyhq.com/x/abc"


@respx.mock
def test_non_string_location_yields_none() -> None:
    job = {"id": "a", "title": "T", "applyUrl": "https://x/a", "location": None}
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"jobs": [job]}))
    assert AshbyFetcher().fetch(_employer())[0].location is None


@respx.mock
def test_empty_board_returns_empty_list() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"jobs": []}))
    assert AshbyFetcher().fetch(_employer()) == []


@respx.mock
def test_missing_jobs_key_raises_fetcherror() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"meta": {}}))
    with pytest.raises(FetchError, match="missing a 'jobs' list"):
        AshbyFetcher().fetch(_employer())


@respx.mock
def test_http_500_raises_fetcherror() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError):
        AshbyFetcher().fetch(_employer())


@respx.mock
def test_no_apply_link_raises_fetcherror() -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(200, json={"jobs": [{"id": "a", "title": "T"}]})
    )
    with pytest.raises(FetchError, match="no apply/job URL"):
        AshbyFetcher().fetch(_employer())
