"""Unit tests for the Greenhouse fetcher (Chunk 4).

Mapping is asserted against a captured real response (`tests/fixtures/greenhouse.json`,
D-019) with HTTP stubbed by respx — no real packets leave. Failure modes (non-200,
non-JSON, malformed shape) must raise `FetchError`, never return garbage or empty.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers.base import FetchError
from vja.fetchers.greenhouse import GreenhouseFetcher
from vja.models import AtsType, Employer

_FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "greenhouse.json").read_text()
)
_URL = "https://boards-api.greenhouse.io/v1/boards/camusenergy/jobs?content=true"


def _employer(slug: str = "camusenergy") -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="Camus Energy",
        ats_type=AtsType.GREENHOUSE,
        ats_slug=slug,
    )


@respx.mock
def test_fetch_maps_every_fixture_job() -> None:
    route = respx.get(_URL).mock(return_value=httpx.Response(200, json=_FIXTURE))

    postings = GreenhouseFetcher().fetch(_employer())

    assert route.called
    assert len(postings) == len(_FIXTURE["jobs"])

    job0 = _FIXTURE["jobs"][0]
    first = postings[0]
    assert first.external_id == str(job0["id"])
    assert first.title == job0["title"]
    assert first.apply_url == job0["absolute_url"]
    assert first.location == job0["location"]["name"]
    assert first.updated_at == job0["updated_at"]
    assert first.raw == job0
    assert first.description == job0["content"]  # inline HTML from ?content=true


@respx.mock
def test_external_id_is_stringified() -> None:
    # Greenhouse ids are integers in JSON; the diff key must be a string (D-016).
    route = respx.get(_URL).mock(
        return_value=httpx.Response(
            200,
            json={"jobs": [{"id": 42, "title": "T", "absolute_url": "https://x/42"}]},
        )
    )
    postings = GreenhouseFetcher().fetch(_employer())
    assert route.called
    assert postings[0].external_id == "42"
    assert isinstance(postings[0].external_id, str)


@respx.mock
def test_missing_location_object_yields_none() -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200, json={"jobs": [{"id": 1, "title": "T", "absolute_url": "https://x/1"}]}
        )
    )
    postings = GreenhouseFetcher().fetch(_employer())
    assert postings[0].location is None


@respx.mock
def test_empty_board_returns_empty_list_not_error() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"jobs": []}))
    assert GreenhouseFetcher().fetch(_employer()) == []


@respx.mock
def test_http_500_raises_fetcherror() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError):
        GreenhouseFetcher().fetch(_employer())


@respx.mock
def test_network_error_raises_fetcherror() -> None:
    respx.get(_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(FetchError):
        GreenhouseFetcher().fetch(_employer())


@respx.mock
def test_non_json_body_raises_fetcherror() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(FetchError):
        GreenhouseFetcher().fetch(_employer())


@respx.mock
def test_missing_jobs_key_raises_fetcherror() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"meta": {}}))
    with pytest.raises(FetchError):
        GreenhouseFetcher().fetch(_employer())


@respx.mock
def test_job_missing_required_field_raises_fetcherror() -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(200, json={"jobs": [{"id": 1, "title": "no url"}]})
    )
    with pytest.raises(FetchError, match="missing required field"):
        GreenhouseFetcher().fetch(_employer())
