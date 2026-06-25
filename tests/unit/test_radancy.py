"""Unit tests for the Radancy / TalentBrew fetcher.

Mapping is asserted against a captured real NextEra response (`tests/fixtures/radancy_list.html`
+ `radancy_detail.html`, D-019); HTTP stubbed by respx. Radancy mirrors Workday's contract:
list-only (the results rows carry no description) + paginate-or-fail + a lazy `fetch_detail`.
``external_id`` is the ``/job/{slug}/{id}`` path (the detail URL needs the slug; the id alone 404s)
— the same path-as-id shape Workday's ``externalPath`` uses (D-032/D-052).
"""

from pathlib import Path

import httpx
import pytest
import respx
from bs4 import BeautifulSoup

from vja.fetchers import radancy
from vja.fetchers.base import FetchError
from vja.fetchers.radancy import RadancyFetcher
from vja.models import AtsType, Employer

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_LIST_HTML = (_FIXTURES / "radancy_list.html").read_text(encoding="utf-8")
_DETAIL_HTML = (_FIXTURES / "radancy_detail.html").read_text(encoding="utf-8")

_ENDPOINT = "https://jobs.test.com"
_LIST_URL = f"{_ENDPOINT}/search-jobs/results"


def _employer() -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="TestCo",
        ats_type=AtsType.RADANCY,
        ats_slug=None,
        endpoint=_ENDPOINT,
    )


def _row(
    i: int, *, location: str | None = "Houston, TX, US", date: str | None = "Jun 24, 2026"
) -> str:
    loc = (
        f'<td class="colLocation"><span class="jobLocation">{location}</span></td>'
        if location
        else "<td class='colLocation'></td>"
    )
    dt = (
        f'<td class="colDate"><span class="jobDate">{date}</span></td>'
        if date
        else "<td class='colDate'></td>"
    )
    # Two jobTitle-link per row (desktop + phone), mirroring the real markup → must dedupe to one.
    return (
        '<tr class="data-row">'
        f'<td class="colTitle"><span class="jobTitle hidden-phone">'
        f'<a class="jobTitle-link" href="/job/eng-{i}/100{i}/">Engineer {i}</a></span>'
        f'<span class="jobTitle visible-phone">'
        f'<a class="jobTitle-link" href="/job/eng-{i}/100{i}/">Engineer {i}</a></span></td>'
        f"{loc}{dt}</tr>"
    )


def _page(rows_html: str, total: int) -> httpx.Response:
    table = (
        f'<table id="searchresults" aria-label="Search results for . '
        f'Page 1 of 1, Results 1 to 25 of {total}"><tbody>{rows_html}</tbody></table>'
    )
    return httpx.Response(200, text=f"<html><body>{table}</body></html>")


# --- Real-fixture golden: lock the actual NextEra markup (D-019) ------------------------------


def test_real_fixture_first_row_maps() -> None:
    soup = BeautifulSoup(_LIST_HTML, "html.parser")
    table = soup.select_one("table#searchresults")
    assert table is not None
    assert radancy._read_total(table, _employer()) == 288  # from the table aria-label

    first = table.select("tbody tr.data-row")[0]
    posting = radancy._map_row(first, "https://jobs.nexteraenergy.com", _employer())

    # external_id = the /job path (slug + numeric req id) — the stable diff key (D-016/D-052)
    assert posting.external_id == (
        "North-Palm-Beach-Assumed-Reinsurance-Claims-Account-Manager-FL-33408/1340304000"
    )
    assert posting.title == "Assumed Reinsurance Claims Account Manager"
    assert posting.apply_url == (
        "https://jobs.nexteraenergy.com/job/"
        "North-Palm-Beach-Assumed-Reinsurance-Claims-Account-Manager-FL-33408/1340304000/"
    )
    assert posting.location == "North Palm Beach, FL, US, 33408"
    assert posting.updated_at == "2026-06-24"  # jobDate "Jun 24, 2026" → ISO (D-030)
    assert posting.description is None  # list-only; description is the lazy detail fetch


# --- fetch() behavior (synthetic pages) -------------------------------------------------------


@respx.mock
def test_fetch_maps_single_page() -> None:
    route = respx.get(_LIST_URL).mock(return_value=_page(_row(0) + _row(1), total=2))

    postings = RadancyFetcher().fetch(_employer())

    assert route.called
    assert [p.external_id for p in postings] == [
        "eng-0/1000",
        "eng-1/1001",
    ]
    first = postings[0]
    assert first.title == "Engineer 0"
    assert first.apply_url == "https://jobs.test.com/job/eng-0/1000/"
    assert first.location == "Houston, TX, US"
    assert first.updated_at == "2026-06-24"


@respx.mock
def test_pagination_assembles_every_page() -> None:
    pages = {1: _row(0) + _row(1), 2: _row(2) + _row(3), 3: _row(4)}

    def by_page(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["CurrentPage"])
        return _page(pages.get(page, ""), total=5)

    route = respx.get(_LIST_URL).mock(side_effect=by_page)

    postings = RadancyFetcher().fetch(_employer())

    assert [p.external_id for p in postings] == [f"eng-{i}/100{i}" for i in range(5)]
    assert route.call_count == 3  # pages 1, 2, 3


@respx.mock
def test_incomplete_fetch_raises_not_partial() -> None:
    # total says 5 but the board yields 3 then an empty page → truncated, must fail loudly.
    def by_page(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["CurrentPage"])
        return _page(_row(0) + _row(1) + _row(2) if page == 1 else "", total=5)

    respx.get(_LIST_URL).mock(side_effect=by_page)

    with pytest.raises(FetchError, match="incomplete"):
        RadancyFetcher().fetch(_employer())


@respx.mock
def test_midpagination_error_raises() -> None:
    def by_page(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["CurrentPage"])
        if page == 2:
            raise httpx.ConnectError("boom")
        return _page(_row(0) + _row(1), total=5)

    respx.get(_LIST_URL).mock(side_effect=by_page)

    with pytest.raises(FetchError):
        RadancyFetcher().fetch(_employer())


@respx.mock
def test_empty_board_returns_empty_list() -> None:
    no_results = '<html><body><div class="search-no-results">No jobs found</div></body></html>'
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, text=no_results))
    assert RadancyFetcher().fetch(_employer()) == []


@respx.mock
def test_missing_results_table_raises() -> None:
    respx.get(_LIST_URL).mock(
        return_value=httpx.Response(200, text="<html><body>nope</body></html>")
    )
    with pytest.raises(FetchError, match="no results table"):
        RadancyFetcher().fetch(_employer())


@respx.mock
def test_unparseable_total_raises() -> None:
    table = (
        '<table id="searchresults" aria-label="Search results"><tbody>'
        + _row(0)
        + "</tbody></table>"
    )
    respx.get(_LIST_URL).mock(return_value=httpx.Response(200, text=table))
    with pytest.raises(FetchError, match="total"):
        RadancyFetcher().fetch(_employer())


@respx.mock
def test_row_without_job_link_raises() -> None:
    bad = '<tr class="data-row"><td class="colTitle">no link</td></tr>'
    respx.get(_LIST_URL).mock(return_value=_page(bad, total=1))
    with pytest.raises(FetchError, match="job link"):
        RadancyFetcher().fetch(_employer())


@respx.mock
def test_row_without_title_raises() -> None:
    bad = '<tr class="data-row"><td><a class="jobTitle-link" href="/job/x/1/"></a></td></tr>'
    respx.get(_LIST_URL).mock(return_value=_page(bad, total=1))
    with pytest.raises(FetchError, match="title"):
        RadancyFetcher().fetch(_employer())


@respx.mock
def test_missing_location_and_date_yield_none() -> None:
    respx.get(_LIST_URL).mock(return_value=_page(_row(0, location=None, date=None), total=1))
    posting = RadancyFetcher().fetch(_employer())[0]
    assert posting.location is None
    assert posting.updated_at is None


@respx.mock
def test_unparseable_date_yields_none() -> None:
    respx.get(_LIST_URL).mock(return_value=_page(_row(0, date="sometime soon"), total=1))
    assert RadancyFetcher().fetch(_employer())[0].updated_at is None


@respx.mock
def test_http_500_raises_fetcherror() -> None:
    respx.get(_LIST_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError):
        RadancyFetcher().fetch(_employer())


# --- fetch_detail() (lazy Layer-2 description) ------------------------------------------------


@respx.mock
def test_fetch_detail_returns_description() -> None:
    eid = "North-Palm-Beach-Assumed-Reinsurance-Claims-Account-Manager-FL-33408/1340304000"
    url = f"{_ENDPOINT}/job/{eid}/"
    route = respx.get(url).mock(return_value=httpx.Response(200, text=_DETAIL_HTML))

    detail = RadancyFetcher().fetch_detail(_employer(), eid)

    assert route.called
    assert detail["description"] and "NextEra Energy" in detail["description"]  # the Layer-2 body
    assert detail["url"] == url


@respx.mock
def test_fetch_detail_error_page_raises() -> None:
    # The id-only / stale path redirects to the portal's error page → must fail, not return junk.
    eid = "x/1"
    respx.get(f"{_ENDPOINT}/job/{eid}/").mock(
        return_value=httpx.Response(
            302, headers={"Location": f"{_ENDPOINT}/errorpage/?errortype=404"}
        )
    )
    respx.get(f"{_ENDPOINT}/errorpage/").mock(
        return_value=httpx.Response(200, text="<html>err</html>")
    )
    with pytest.raises(FetchError, match="error page"):
        RadancyFetcher().fetch_detail(_employer(), eid)


@respx.mock
def test_fetch_detail_http_error_raises() -> None:
    respx.get(f"{_ENDPOINT}/job/x/1/").mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError):
        RadancyFetcher().fetch_detail(_employer(), "x/1")
