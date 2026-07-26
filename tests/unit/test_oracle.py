"""Unit tests for the Oracle HCM / ORC (Candidate Experience) fetcher.

Mapping is asserted against a captured real Southern Company response (`tests/fixtures/oracle.json`,
D-019); HTTP stubbed by respx. Oracle mirrors iCIMS/Workday's contract: list-only (the
`External*Str` description fields are empty in list mode) + paginate-or-fail + a lazy
`fetch_detail`. The apply URL is *constructed* from `careers_url` + `Id`; pagination appends offset.
"""

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from vja.fetchers import oracle
from vja.fetchers.base import FetchError
from vja.fetchers.oracle import OracleFetcher
from vja.models import AtsType, Employer

_FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "oracle.json").read_text()
)
_REQS: list[dict[str, Any]] = _FIXTURE["items"][0]["requisitionList"]
_DETAIL: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "oracle_detail.json").read_text()
)
_HOST = "https://emje.fa.us6.oraclecloud.com"
_LIST = f"{_HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
# The seeded list endpoint (host + site + finder), to which the fetcher appends `,limit,offset`.
_ENDPOINT = (
    f"{_LIST}?onlyData=true&expand=requisitionList.secondaryLocations"
    "&finder=findReqs;siteNumber=CX_1001"
)
_CAREERS = f"{_HOST}/hcmUI/CandidateExperience/en/sites/SouthernCompanyJobs"
_DETAIL_RESOURCE = f"{_HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"


def _employer(endpoint: str = _ENDPOINT, careers_url: str | None = _CAREERS) -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="Southern Company",
        ats_type=AtsType.ORACLE_HCM,
        endpoint=endpoint,
        careers_url=careers_url,
    )


def _req(i: int) -> dict[str, Any]:
    return {
        "Id": str(16000 + i),
        "Title": f"Engineer {i}",
        "PrimaryLocation": "Atlanta, GA, United States",
        "PostedDate": "2026-06-23",
    }


def _page(reqs: list[dict[str, Any]], total: int) -> httpx.Response:
    return httpx.Response(200, json={"items": [{"TotalJobsCount": total, "requisitionList": reqs}]})


def _offset(request: httpx.Request) -> int:
    match = re.search(r"offset=(\d+)", str(request.url))
    return int(match.group(1)) if match else 0


@respx.mock
def test_maps_fixture_reqs() -> None:
    route = respx.get(url__startswith=_ENDPOINT).mock(return_value=_page(_REQS, total=len(_REQS)))

    postings = OracleFetcher().fetch(_employer())

    assert route.called
    assert len(postings) == len(_REQS)
    req0, first = _REQS[0], postings[0]
    assert first.external_id == str(req0["Id"])  # the diff key (D-016)
    assert first.title == req0["Title"]
    assert first.apply_url == f"{_CAREERS}/job/{req0['Id']}"  # constructed from careers_url + Id
    assert first.location == req0["PrimaryLocation"]  # already readable
    assert first.updated_at == req0["PostedDate"]  # real date (freshness, D-030)
    assert first.description is None  # list-only; description is a lazy detail fetch
    assert first.raw == req0


@respx.mock
def test_pagination_assembles_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oracle, "_PAGE_SIZE", 2)
    reqs = [_req(i) for i in range(5)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        start = _offset(request)
        return _page(reqs[start : start + 2], total=5)

    route = respx.get(url__startswith=_ENDPOINT).mock(side_effect=by_offset)

    postings = OracleFetcher().fetch(_employer())

    assert [p.external_id for p in postings] == [r["Id"] for r in reqs]
    assert route.call_count == 3  # offsets 0, 2, 4


@respx.mock
def test_incomplete_fetch_raises_not_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oracle, "_PAGE_SIZE", 2)
    reqs = [_req(i) for i in range(3)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        start = _offset(request)
        return _page(reqs[start : start + 2], total=5)

    respx.get(url__startswith=_ENDPOINT).mock(side_effect=by_offset)

    with pytest.raises(FetchError, match="incomplete"):
        OracleFetcher().fetch(_employer())


@respx.mock
def test_overcount_fetch_raises_not_partial() -> None:
    respx.get(url__startswith=_ENDPOINT).mock(return_value=_page([_req(0), _req(1)], total=1))

    with pytest.raises(FetchError, match="incomplete"):
        OracleFetcher().fetch(_employer())


@respx.mock
def test_total_change_midfetch_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oracle, "_PAGE_SIZE", 2)
    reqs = [_req(i) for i in range(5)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        start = _offset(request)
        return _page(reqs[start : start + 2], total=5 if start == 0 else 6)

    respx.get(url__startswith=_ENDPOINT).mock(side_effect=by_offset)

    with pytest.raises(FetchError, match="total changed"):
        OracleFetcher().fetch(_employer())


@respx.mock
def test_midpagination_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oracle, "_PAGE_SIZE", 2)
    reqs = [_req(i) for i in range(5)]

    def by_offset(request: httpx.Request) -> httpx.Response:
        start = _offset(request)
        if start == 2:
            raise httpx.ConnectError("boom")
        return _page(reqs[start : start + 2], total=5)

    respx.get(url__startswith=_ENDPOINT).mock(side_effect=by_offset)

    with pytest.raises(FetchError):
        OracleFetcher().fetch(_employer())


@respx.mock
def test_empty_board_returns_empty_list() -> None:
    respx.get(url__startswith=_ENDPOINT).mock(return_value=_page([], total=0))
    assert OracleFetcher().fetch(_employer()) == []


@respx.mock
def test_missing_requisitionlist_raises_fetcherror() -> None:
    # Without the `expand=requisitionList...`, the API returns search metadata but no list.
    resp = httpx.Response(200, json={"items": [{"TotalJobsCount": 5}]})
    respx.get(url__startswith=_ENDPOINT).mock(return_value=resp)
    with pytest.raises(FetchError, match="requisitionList"):
        OracleFetcher().fetch(_employer())


@respx.mock
def test_missing_total_raises_fetcherror() -> None:
    resp = httpx.Response(200, json={"items": [{"requisitionList": [_req(0)]}]})
    respx.get(url__startswith=_ENDPOINT).mock(return_value=resp)
    with pytest.raises(FetchError, match="TotalJobsCount"):
        OracleFetcher().fetch(_employer())


@respx.mock
def test_missing_items_raises_fetcherror() -> None:
    respx.get(url__startswith=_ENDPOINT).mock(return_value=httpx.Response(200, json={"items": []}))
    with pytest.raises(FetchError, match="items"):
        OracleFetcher().fetch(_employer())


@respx.mock
def test_http_500_raises_fetcherror() -> None:
    respx.get(url__startswith=_ENDPOINT).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError):
        OracleFetcher().fetch(_employer())


@respx.mock
def test_non_json_raises_fetcherror() -> None:
    respx.get(url__startswith=_ENDPOINT).mock(return_value=httpx.Response(200, text="<html/>"))
    with pytest.raises(FetchError):
        OracleFetcher().fetch(_employer())


@respx.mock
def test_req_missing_id_raises_fetcherror() -> None:
    respx.get(url__startswith=_ENDPOINT).mock(return_value=_page([{"Title": "No id"}], total=1))
    with pytest.raises(FetchError, match="Id"):
        OracleFetcher().fetch(_employer())


@respx.mock
def test_req_missing_title_raises_fetcherror() -> None:
    respx.get(url__startswith=_ENDPOINT).mock(return_value=_page([{"Id": "1"}], total=1))
    with pytest.raises(FetchError, match="Title"):
        OracleFetcher().fetch(_employer())


def test_missing_careers_url_raises_fetcherror() -> None:
    # apply-URL construction needs the CE site base; a missing one is a loud config defect.
    with pytest.raises(FetchError, match="careers_url"):
        OracleFetcher().fetch(_employer(careers_url=None))


def test_endpoint_without_sitenumber_raises_on_detail() -> None:
    # `fetch_detail` parses host + siteNumber off the list endpoint; a missing one fails loudly.
    bad = _employer(endpoint=f"{_LIST}?onlyData=true&finder=findReqs")
    with pytest.raises(FetchError, match="siteNumber"):
        OracleFetcher().fetch_detail(bad, "16280")


@respx.mock
def test_fetch_detail_returns_item() -> None:
    route = respx.get(url__startswith=_DETAIL_RESOURCE).mock(
        return_value=httpx.Response(200, json=_DETAIL)
    )

    detail = OracleFetcher().fetch_detail(_employer(), "16280")

    assert route.called
    # The detail URL carries the parsed siteNumber + the requested Id.
    sent = str(route.calls[0].request.url)
    assert "siteNumber=CX_1001" in sent
    assert "Id=16280" in sent
    assert detail["ExternalDescriptionStr"]  # the Layer-2 body


@respx.mock
def test_fetch_detail_missing_items_raises() -> None:
    respx.get(url__startswith=_DETAIL_RESOURCE).mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    with pytest.raises(FetchError, match="items"):
        OracleFetcher().fetch_detail(_employer(), "16280")


@respx.mock
def test_fetch_detail_http_error_raises() -> None:
    respx.get(url__startswith=_DETAIL_RESOURCE).mock(return_value=httpx.Response(404))
    with pytest.raises(FetchError):
        OracleFetcher().fetch_detail(_employer(), "16280")


def test_detail_description_joins_the_external_body_fields() -> None:
    item = _DETAIL["items"][0]
    body = OracleFetcher().detail_description(item)

    assert body is not None
    assert item["ExternalDescriptionStr"][:40] in body


def test_detail_description_never_reads_the_internal_fields() -> None:
    # `Internal*Str` is written for the employee-facing site; it must never reach a candidate.
    item = {
        "ExternalDescriptionStr": "Public description.",
        "InternalDescriptionStr": "INTERNAL ONLY — comp band + backfill reason.",
        "InternalQualificationsStr": "INTERNAL ONLY",
    }
    body = OracleFetcher().detail_description(item)

    assert body == "Public description."


def test_detail_description_is_none_when_the_body_fields_are_empty() -> None:
    assert OracleFetcher().detail_description({"ExternalDescriptionStr": "  "}) is None
