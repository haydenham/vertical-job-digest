"""Offline contract tests for the Paylocity Recruiting fetcher (D-076)."""

from pathlib import Path

import httpx
import pytest
import respx

from vja.fetchers.base import FetchError
from vja.fetchers.paylocity import PaylocityFetcher
from vja.models import AtsType, Employer

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_LIST_HTML = (_FIXTURES / "paylocity_list.html").read_text(encoding="utf-8")
_DETAIL_HTML = (_FIXTURES / "paylocity_detail.html").read_text(encoding="utf-8")
_ENDPOINT = (
    "https://recruiting.paylocity.com/recruiting/jobs/All/"
    "eaf316dd-b54d-49a6-b1d8-1ab594e6a319/Veryon"
)


def _employer() -> Employer:
    return Employer(
        id=1,
        vertical="aviation_software",
        name="Veryon",
        ats_type=AtsType.PAYLOCITY,
        endpoint=_ENDPOINT,
    )


@respx.mock
def test_real_fixture_maps_complete_jobs_list() -> None:
    route = respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, text=_LIST_HTML))

    postings = PaylocityFetcher().fetch(_employer())

    assert route.call_count == 1
    assert len(postings) == 2
    first = postings[0]
    assert first.external_id == "4324344"
    assert first.title == "Sales Engineer"
    assert first.apply_url == "https://recruiting.paylocity.com/Recruiting/jobs/Apply/4324344"
    assert first.location == "USA (Remote)"
    assert first.updated_at == "2026-07-10T14:57:25-05:00"
    assert first.description is None
    assert first.raw["HiringDepartment"] == "Sales"
    assert postings[1].location == "USA"  # nested fallback when LocationName is empty


@respx.mock
def test_valid_empty_board_returns_empty_list() -> None:
    html = '<script>window.pageData = {"Jobs": []};</script>'
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, text=html))
    assert PaylocityFetcher().fetch(_employer()) == []


@pytest.mark.parametrize(
    "html, message",
    [
        ("<html>no page data</html>", "window.pageData"),
        ("<script>window.pageData = {nope};</script>", "invalid JSON"),
        ('<script>window.pageData = {"Other": []};</script>', "Jobs"),
    ],
)
@respx.mock
def test_malformed_board_fails_loudly(html: str, message: str) -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, text=html))
    with pytest.raises(FetchError, match=message):
        PaylocityFetcher().fetch(_employer())


@respx.mock
def test_invalid_job_entry_fails_loudly() -> None:
    html = '<script>window.pageData = {"Jobs": [{"JobTitle": "No id"}]};</script>'
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, text=html))
    with pytest.raises(FetchError, match="JobId"):
        PaylocityFetcher().fetch(_employer())


@respx.mock
def test_null_job_id_fails_loudly() -> None:
    html = '<script>window.pageData = {"Jobs": [{"JobId": null, "JobTitle": "No id"}]};</script>'
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, text=html))
    with pytest.raises(FetchError, match="empty required field"):
        PaylocityFetcher().fetch(_employer())


@respx.mock
def test_http_failure_raises_fetcherror() -> None:
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError, match="paylocity fetch failed"):
        PaylocityFetcher().fetch(_employer())


@respx.mock
def test_fetch_detail_uses_description_section() -> None:
    url = "https://recruiting.paylocity.com/Recruiting/jobs/Details/4324344"
    respx.get(url).mock(return_value=httpx.Response(200, text=_DETAIL_HTML))

    detail = PaylocityFetcher().fetch_detail(_employer(), "4324344")

    assert "supports high-value aviation software" in (detail["description"] or "")
    assert "Five years" not in (detail["description"] or "")
    assert detail["url"] == url


@respx.mock
def test_fetch_detail_without_description_fails_loudly() -> None:
    url = "https://recruiting.paylocity.com/Recruiting/jobs/Details/4324344"
    respx.get(url).mock(return_value=httpx.Response(200, text="<html></html>"))
    with pytest.raises(FetchError, match="no description"):
        PaylocityFetcher().fetch_detail(_employer(), "4324344")
