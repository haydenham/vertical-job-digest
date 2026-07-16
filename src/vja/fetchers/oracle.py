"""Oracle HCM / ORC (Candidate Experience) Layer-1 fetcher (`docs/05`, `docs/07`).

Oracle Recruiting Cloud exposes a clean, unauthenticated **Candidate-Experience REST API** on each
tenant's Oracle Cloud host. The shape is uniform across tenants, so this is one generic per-platform
fetcher, never a per-company scraper (D-017/D-004). Hosts and site numbers differ per tenant, so —
like iCIMS/Workday — the seed `endpoint` is **explicit per-tenant** (not slug-derived) and points at
the list resource:

``GET {host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions``
``?onlyData=true&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber={CX_n}`` →
``{"items": [ {"TotalJobsCount": int, "requisitionList": [ {...} ]} ]}``.

The contract mirrors **iCIMS/Workday**: list-only + paginate-or-fail + a lazy detail fetch.

- **List-only.** The list carries the title, readable ``PrimaryLocation``, and ``PostedDate``, but
  the ``External*Str`` description fields come back **empty in list mode**. The apply URL is
  *constructed* (``{careers_url}/job/{Id}`` — verified to resolve), so the apply link needs no
  detail fetch (D-008). The description lives only on the detail resource and is fetched lazily,
  per in-scope survivor, by Layer-2 extraction (`extract.py`) via `fetch_detail` (cost discipline,
  D-035), exactly like Workday.
- **Paginate fully or fail.** ``TotalJobsCount`` drives pagination (page size + offset are appended
  to the ``finder`` as sub-params, ``,limit={N},offset={M}``); a short final tally is a hard
  `FetchError` (false-closure guard, `docs/08`).

Mapping (`docs/05`): ``external_id = Id`` (the stable requisition id + the diff key D-016, and the
apply-URL path), ``apply_url`` constructed from ``careers_url`` + id, ``title = Title``,
``location = PrimaryLocation`` (already readable), ``updated_at = PostedDate`` (a D-030 freshness
win). ``description = None`` (lazy — see `fetch_detail`).
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from vja.fetchers.base import FetchError
from vja.fetchers.endpoints import build_endpoint
from vja.models import AtsType, Employer, RawPosting

_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"
_TIMEOUT = 30.0
_PAGE_SIZE = 100  # the CE API honours an explicit limit; 100 keeps requests few + polite
_MAX_PAGES = 200  # safety cap against a bad `TotalJobsCount` (200×100 = 20000, above any tenant)

# The detail resource, built from the tenant host + siteNumber parsed off the seeded list endpoint
# so list + detail stay consistent from one seed field. `expand=all` yields the description HTML.
_DETAIL_PATH = (
    "/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
    "?onlyData=true&expand=all&finder=ById;Id={external_id},siteNumber={site}"
)
_SITE_NUMBER_RE = re.compile(r"siteNumber=(CX_\d+)")


class OracleFetcher:
    """Fetches open postings from an Oracle ORC Candidate-Experience board. Pure read (`docs/05`).

    A `client` may be injected (tests / connection reuse); otherwise a short-lived one is created
    per fetch with an identifiable User-Agent (politeness — `docs/05`).
    """

    ats_type: AtsType = AtsType.ORACLE_HCM

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, employer: Employer) -> list[RawPosting]:
        url = build_endpoint(employer)
        apply_base = _apply_base(employer)
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            return _paginate(client, url, apply_base, employer)
        finally:
            if self._client is None:
                client.close()

    def fetch_detail(self, employer: Employer, external_id: str) -> dict[str, Any]:
        """Fetch one requisition's full detail — the Layer-2 body (``ExternalDescriptionStr``).

        The host + ``siteNumber`` are parsed off the seeded list endpoint, so one seed field drives
        both calls. Returns the detail item dict for extraction to read; raises `FetchError`.
        """
        detail_url = _detail_url(employer)
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            response = client.get(detail_url.format(external_id=external_id))
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise FetchError(f"oracle detail fetch failed for {employer.name!r}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FetchError(f"oracle detail non-JSON for {employer.name!r}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            raise FetchError(f"oracle detail for {employer.name!r} missing an 'items' entry")
        return items[0]


def _paginate(
    client: httpx.Client, url: str, apply_base: str, employer: Employer
) -> list[RawPosting]:
    postings: list[RawPosting] = []
    total: int | None = None

    for page in range(_MAX_PAGES):
        item = _get_page(client, url, page * _PAGE_SIZE, employer)
        page_total = _read_total(item, employer)
        if total is None:
            total = page_total
        elif page_total != total:
            raise FetchError(
                f"oracle total changed during fetch for {employer.name!r}: {total} → {page_total}"
            )
        reqs = item["requisitionList"]
        for req in reqs:
            postings.append(_map_req(req, apply_base, employer))
        if not reqs or len(postings) >= total:
            break

    # Completeness guard: only an exact tally is safe. Both a short and an over-counted snapshot
    # can hide pagination drift that the diff would otherwise interpret as real board churn.
    if total is None or len(postings) != total:
        expected = total if total is not None else "unknown"
        raise FetchError(
            f"oracle fetch for {employer.name!r} incomplete: got {len(postings)} of {expected}"
        )
    return postings


def _get_page(client: httpx.Client, url: str, offset: int, employer: Employer) -> dict[str, Any]:
    # limit/offset are `finder` sub-params (comma-separated), appended to the seeded URL whose
    # `finder=...` must be the final query param. httpx params can't express this (Oracle wants them
    # inside the finder value), so they are string-appended.
    page_url = f"{url},limit={_PAGE_SIZE},offset={offset}"
    try:
        response = client.get(page_url)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise FetchError(
            f"oracle fetch failed for {employer.name!r} (offset {offset}): {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise FetchError(f"oracle returned non-JSON for {employer.name!r}: {exc}") from exc

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise FetchError(f"oracle response for {employer.name!r} missing an 'items' entry")
    item = items[0]
    if not isinstance(item.get("requisitionList"), list):
        raise FetchError(
            f"oracle response for {employer.name!r} missing a 'requisitionList' "
            "(is `expand=requisitionList...` in the endpoint?)"
        )
    return item


def _read_total(item: dict[str, Any], employer: Employer) -> int:
    total = item.get("TotalJobsCount")
    if not isinstance(total, int):
        raise FetchError(f"oracle response for {employer.name!r} missing 'TotalJobsCount'")
    return total


def _map_req(req: dict[str, Any], apply_base: str, employer: Employer) -> RawPosting:
    """Map one ORC requisition to a `RawPosting`; raise `FetchError` on a missing field."""
    if not isinstance(req, dict):
        raise FetchError(f"oracle requisition for {employer.name!r} is not an object")
    external_id = req.get("Id")
    title = req.get("Title")
    if external_id in (None, ""):
        raise FetchError(f"oracle requisition for {employer.name!r} missing 'Id'")
    if not isinstance(title, str) or not title:
        raise FetchError(f"oracle requisition for {employer.name!r} missing 'Title'")

    location = req.get("PrimaryLocation")
    posted = req.get("PostedDate")
    return RawPosting(
        external_id=str(external_id),
        title=title,
        apply_url=f"{apply_base}/job/{external_id}",
        location=location if isinstance(location, str) and location else None,
        updated_at=posted if isinstance(posted, str) and posted else None,
        raw=req,
        description=None,  # list-only; the description is a lazy Layer-2 fetch (`fetch_detail`)
    )


def _apply_base(employer: Employer) -> str:
    """The Candidate-Experience site base for apply-URL construction (``{base}/job/{Id}``)."""
    if not employer.careers_url:
        raise FetchError(
            f"oracle employer {employer.name!r} has no careers_url to build apply URLs from"
        )
    return employer.careers_url.rstrip("/")


def _detail_url(employer: Employer) -> str:
    """Build the detail-resource URL template (``{external_id}`` left to format) from the seeded
    list endpoint's host + ``siteNumber`` — one seed field drives both calls. `FetchError` if the
    endpoint lacks a parseable host or siteNumber (a config defect surfaced loudly)."""
    endpoint = build_endpoint(employer)
    split = urlsplit(endpoint)
    match = _SITE_NUMBER_RE.search(endpoint)
    if not split.scheme or not split.netloc or match is None:
        raise FetchError(
            f"oracle endpoint for {employer.name!r} lacks a host or siteNumber: {endpoint!r}"
        )
    return f"{split.scheme}://{split.netloc}{_DETAIL_PATH}".replace("{site}", match.group(1))
