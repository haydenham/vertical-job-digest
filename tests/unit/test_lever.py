"""Unit tests for the Lever fetcher (Chunk 5).

Mapping asserted against a captured real response (`tests/fixtures/lever.json`, D-019)
with HTTP stubbed by respx. Lever returns a bare JSON array (no wrapper object).
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers.base import FetchError
from vja.fetchers.lever import LeverFetcher
from vja.models import AtsType, Employer

_FIXTURE: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "lever.json").read_text()
)
_URL = "https://api.lever.co/v0/postings/voltus?mode=json"


def _employer(slug: str = "voltus") -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="Voltus",
        ats_type=AtsType.LEVER,
        ats_slug=slug,
    )


@respx.mock
def test_fetch_maps_every_fixture_job() -> None:
    route = respx.get(_URL).mock(return_value=httpx.Response(200, json=_FIXTURE))

    postings = LeverFetcher().fetch(_employer())

    assert route.called
    assert len(postings) == len(_FIXTURE)

    job0 = _FIXTURE[0]
    first = postings[0]
    assert first.external_id == str(job0["id"])
    assert first.title == job0["text"]
    assert first.apply_url == job0["applyUrl"]
    assert first.location == job0["categories"]["location"]
    assert first.raw == job0
    assert first.description == job0["descriptionPlain"]


@respx.mock
def test_description_falls_back_to_html_when_plain_is_empty() -> None:
    # Some Lever postings leave descriptionPlain empty but populate `description` (HTML).
    job = {
        "id": "abc",
        "text": "Engineer",
        "applyUrl": "https://x/abc/apply",
        "descriptionPlain": "",
        "description": "<p>Real body</p>",
    }
    respx.get(_URL).mock(return_value=httpx.Response(200, json=[job]))
    assert LeverFetcher().fetch(_employer())[0].description == "<p>Real body</p>"


@respx.mock
def test_apply_url_falls_back_to_hosted_url() -> None:
    job = {
        "id": "abc",
        "text": "Engineer",
        "hostedUrl": "https://jobs.lever.co/x/abc",
        "categories": {"location": "Remote"},
    }
    respx.get(_URL).mock(return_value=httpx.Response(200, json=[job]))
    postings = LeverFetcher().fetch(_employer())
    assert postings[0].apply_url == "https://jobs.lever.co/x/abc"


@respx.mock
def test_missing_categories_yields_none_location() -> None:
    job = {"id": "abc", "text": "Engineer", "applyUrl": "https://x/abc/apply"}
    respx.get(_URL).mock(return_value=httpx.Response(200, json=[job]))
    assert LeverFetcher().fetch(_employer())[0].location is None


@respx.mock
def test_empty_board_returns_empty_list() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json=[]))
    assert LeverFetcher().fetch(_employer()) == []


@respx.mock
def test_object_instead_of_array_raises_fetcherror() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"jobs": []}))
    with pytest.raises(FetchError, match="not a JSON array"):
        LeverFetcher().fetch(_employer())


@respx.mock
def test_http_500_raises_fetcherror() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError):
        LeverFetcher().fetch(_employer())


@respx.mock
def test_no_apply_link_raises_fetcherror() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json=[{"id": "a", "text": "T"}]))
    with pytest.raises(FetchError, match="no apply/hosted URL"):
        LeverFetcher().fetch(_employer())
