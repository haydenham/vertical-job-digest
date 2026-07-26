"""Offline contract tests for the generic Rippling ATS fetcher."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers.base import FetchError
from vja.fetchers.rippling import RipplingFetcher
from vja.models import AtsType, Employer

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_LIST: list[dict[str, Any]] = json.loads((_FIXTURES / "rippling_list.json").read_text())
_DETAIL: dict[str, Any] = json.loads((_FIXTURES / "rippling_detail.json").read_text())
_LIST_URL = "https://api.rippling.com/platform/api/ats/v1/board/example/jobs"
_DETAIL_URL = f"{_LIST_URL}/f7008ce4-5157-4ba9-b75b-ed2a6448b579"


def _employer() -> Employer:
    return Employer(
        id=1,
        vertical="aviation_software",
        name="Example Aviation",
        ats_type=AtsType.RIPPLING,
        ats_slug="example",
    )


@respx.mock
def test_real_fixture_maps_complete_list_without_descriptions() -> None:
    route = respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=_LIST))

    postings = RipplingFetcher().fetch(_employer())

    assert route.call_count == 1
    assert len(postings) == 4
    first = postings[0]
    assert first.external_id == "f7008ce4-5157-4ba9-b75b-ed2a6448b579"
    assert first.title == "Product Marketing Manager"
    # Rippling supplies the apply URL; it is never constructed from the slug + id.
    assert first.apply_url == (
        "https://ats.rippling.com/portside/jobs/f7008ce4-5157-4ba9-b75b-ed2a6448b579"
    )
    assert first.location == "Remote (United States)"
    assert first.updated_at is None
    assert first.description is None
    assert first.raw["department"]["label"] == "Sales & Marketing"
    assert postings[2].location == "Canada"


@respx.mock
def test_valid_empty_board_is_authoritative_zero_openings() -> None:
    """A clean 200 with no jobs means zero open, not a failure — the single-response guard."""
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=[]))
    assert RipplingFetcher().fetch(_employer()) == []


@pytest.mark.parametrize(
    "job, expected",
    [
        ({"workLocation": {"label": "Austin, TX"}}, "Austin, TX"),
        ({"workLocation": {"label": "   "}}, None),
        ({"workLocation": {}}, None),
        ({"workLocation": "Remote"}, None),
        ({}, None),
    ],
)
@respx.mock
def test_location_falls_back_to_none_without_a_usable_label(
    job: dict[str, Any], expected: str | None
) -> None:
    entry = {"uuid": "u1", "name": "Engineer", "url": "https://x/1", **job}
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=[entry]))
    assert RipplingFetcher().fetch(_employer())[0].location == expected


@pytest.mark.parametrize("payload", [{}, {"jobs": []}, "nope", 7])
@respx.mock
def test_non_list_response_fails_closed(payload: Any) -> None:
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(FetchError, match="not a job list"):
        RipplingFetcher().fetch(_employer())


@pytest.mark.parametrize(
    "job, message",
    [
        ({"name": "No id", "url": "https://x/1"}, "uuid"),
        ({"uuid": "u1", "url": "https://x/1"}, "name"),
        ({"uuid": "u1", "name": "No url"}, "url"),
        ({"uuid": "  ", "name": "Engineer", "url": "https://x/1"}, "empty required field"),
        ({"uuid": "u1", "name": "  ", "url": "https://x/1"}, "empty required field"),
        ({"uuid": "u1", "name": "Engineer", "url": ""}, "empty required field"),
        ({"uuid": 12, "name": "Engineer", "url": "https://x/1"}, "empty required field"),
        ("not an object", "not an object"),
    ],
)
@respx.mock
def test_bad_job_fails_entire_list(job: Any, message: str) -> None:
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=[job]))
    with pytest.raises(FetchError, match=message):
        RipplingFetcher().fetch(_employer())


@respx.mock
def test_one_job_across_many_locations_collapses_to_a_single_posting() -> None:
    """Rippling denormalizes (job × location); the locations merge, the job does not split."""
    entries = [
        {
            "uuid": "u1",
            "name": "Data Scientist",
            "url": "https://x/1",
            "department": {"label": "Engineering"},
            "workLocation": {"label": label},
        }
        for label in ("Canberra, Australia", "Collingwood, Australia", "Austin, TX")
    ]
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=entries))

    postings = RipplingFetcher().fetch(_employer())

    assert len(postings) == 1
    assert postings[0].external_id == "u1"
    # Sorted, so a reordered board cannot flip `content_hash` (D-088 churn guard).
    assert postings[0].location == "Austin, TX; Canberra, Australia; Collingwood, Australia"


@respx.mock
def test_collapsed_locations_are_order_independent() -> None:
    def entry(label: str) -> dict[str, Any]:
        return {
            "uuid": "u1",
            "name": "Engineer",
            "url": "https://x/1",
            "workLocation": {"label": label},
        }

    route = respx.get(_LIST_URL)
    route.mock(return_value=httpx.Response(200, json=[entry("Austin, TX"), entry("Denver, CO")]))
    first = RipplingFetcher().fetch(_employer())[0].location
    route.mock(return_value=httpx.Response(200, json=[entry("Denver, CO"), entry("Austin, TX")]))
    assert RipplingFetcher().fetch(_employer())[0].location == first


@respx.mock
def test_duplicate_ids_disagreeing_beyond_location_still_fail_closed() -> None:
    """The narrowed D-016/D-088 guard: a real integrity violation is never collapsed."""
    entries = [
        {"uuid": "u1", "name": "Engineer", "url": "https://x/1", "workLocation": {"label": "A"}},
        {"uuid": "u1", "name": "Designer", "url": "https://x/1", "workLocation": {"label": "B"}},
    ]
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=entries))
    with pytest.raises(FetchError, match="conflicting fields"):
        RipplingFetcher().fetch(_employer())


@respx.mock
def test_exactly_duplicated_entries_collapse_without_error() -> None:
    job = {"uuid": "u1", "name": "Engineer", "url": "https://x/1", "workLocation": {"label": "A"}}
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, json=[job, job]))

    postings = RipplingFetcher().fetch(_employer())

    assert len(postings) == 1
    assert postings[0].location == "A"


@respx.mock
def test_http_and_non_json_fail_loudly_never_as_zero_postings() -> None:
    route = respx.get(_LIST_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError, match="list fetch failed"):
        RipplingFetcher().fetch(_employer())
    # An unknown slug is a clean 404 upstream — still a failure, never "closed everything".
    route.mock(return_value=httpx.Response(404))
    with pytest.raises(FetchError, match="list fetch failed"):
        RipplingFetcher().fetch(_employer())
    route.mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    with pytest.raises(FetchError, match="non-JSON"):
        RipplingFetcher().fetch(_employer())


@respx.mock
def test_detail_returns_the_full_payload() -> None:
    route = respx.get(_DETAIL_URL).mock(return_value=httpx.Response(200, json=_DETAIL))

    detail = RipplingFetcher().fetch_detail(_employer(), "f7008ce4-5157-4ba9-b75b-ed2a6448b579")

    assert route.call_count == 1
    assert detail["name"] == "Product Marketing Manager"
    assert set(detail["description"]) == {"company", "role"}


@pytest.mark.parametrize(
    "payload",
    [
        {"uuid": "u1"},
        {"uuid": "u1", "description": {}},
        {"uuid": "u1", "description": {"role": "   ", "company": ""}},
        {"uuid": "u1", "description": ""},
        {"uuid": "u1", "description": []},
    ],
)
@respx.mock
def test_detail_without_a_body_fails_loudly(payload: Any) -> None:
    respx.get(_DETAIL_URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(FetchError, match="missing job description"):
        RipplingFetcher().fetch_detail(_employer(), "f7008ce4-5157-4ba9-b75b-ed2a6448b579")


@respx.mock
def test_non_object_detail_fails_loudly() -> None:
    respx.get(_DETAIL_URL).mock(return_value=httpx.Response(200, json=[1, 2]))
    with pytest.raises(FetchError, match="not an object"):
        RipplingFetcher().fetch_detail(_employer(), "f7008ce4-5157-4ba9-b75b-ed2a6448b579")


@respx.mock
def test_detail_http_and_non_json_fail_loudly() -> None:
    route = respx.get(_DETAIL_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(FetchError, match="detail fetch failed"):
        RipplingFetcher().fetch_detail(_employer(), "f7008ce4-5157-4ba9-b75b-ed2a6448b579")
    route.mock(return_value=httpx.Response(200, text="not json"))
    with pytest.raises(FetchError, match="non-JSON"):
        RipplingFetcher().fetch_detail(_employer(), "f7008ce4-5157-4ba9-b75b-ed2a6448b579")


def test_detail_description_joins_role_before_company() -> None:
    """Rippling splits the body in two; `role` is the posting, `company` is boilerplate."""
    body = RipplingFetcher().detail_description(
        {"description": {"company": "About us.", "role": "Build things."}}
    )
    assert body == "Build things.\n\nAbout us."


def test_detail_description_reads_the_real_fixture_body() -> None:
    body = RipplingFetcher().detail_description(_DETAIL)
    fragments = _DETAIL["description"]

    assert body is not None
    assert body.startswith(fragments["role"].strip()[:60])
    assert fragments["company"].strip()[:60] in body


@pytest.mark.parametrize(
    "description, expected",
    [
        ({"role": "Only the role."}, "Only the role."),
        ({"company": "Only boilerplate."}, "Only boilerplate."),
        ("a bare string body", "a bare string body"),
        ({"role": "", "company": "  "}, None),
        ({"role": 12}, None),
        (None, None),
        ([], None),
    ],
)
def test_detail_description_handles_partial_and_unexpected_shapes(
    description: Any, expected: str | None
) -> None:
    assert RipplingFetcher().detail_description({"description": description}) == expected
