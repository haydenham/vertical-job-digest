"""Workday `cxs` Layer-1 fetcher (`docs/05`, `docs/07`).

Endpoint (per-tenant; the seed `endpoint` column is authoritative):
``POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`` with body
``{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}``. The response carries `total`
plus one `jobPostings` page; we page by `offset`.

Two things make Workday unlike the Tier-A fetchers, and both shape this module:

- **It is the one paginated source.** We page until we've collected `total`; **any page failure
  raises `FetchError` and we return nothing** — a partial list would read as mass closures, the
  highest-stakes guard (`docs/08`, DECISIONS false-closure note). A short final tally vs. `total`
  is also a hard failure, never a silent partial.
- **The cxs list omits the job description**, so this is list-only (`description=None`). The full
  description is a Layer-2 concern, fetched lazily per new/changed posting later — fetching it here
  would mean hundreds of needless requests per big tenant for data Layer 1 doesn't use (D-026 era).

Mapping (confirmed against a live PJM response, D-019): ``external_id = externalPath`` (stable,
unique — the diff key D-016), ``apply_url`` = the public board URL built from the cxs host + site +
``externalPath``, ``title``, ``location = locationsText``. `postedOn` is a relative string
("Posted 2 Days Ago"), so `updated_at` stays None (a known weak spot for D-030 freshness).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from vja.fetchers.base import FetchError
from vja.fetchers.endpoints import build_endpoint
from vja.models import AtsType, Employer, RawPosting

_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"
_TIMEOUT = 20.0
_PAGE_SIZE = 20
_MAX_PAGES = 200  # safety cap against a bad `total` (200×20 = 4000, far above any real tenant)


class WorkdayFetcher:
    """Fetches open postings from a Workday `cxs` job board. Pure read (`docs/05`).

    A `client` may be injected (tests / connection reuse); otherwise a short-lived one is created
    per fetch with an identifiable User-Agent (politeness — `docs/05`).
    """

    ats_type: AtsType = AtsType.WORKDAY

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, employer: Employer) -> list[RawPosting]:
        url = build_endpoint(employer)
        base, site = _board_base_and_site(url, employer)
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            return _paginate(client, url, base, site, employer)
        finally:
            if self._client is None:
                client.close()


def _paginate(
    client: httpx.Client, url: str, base: str, site: str, employer: Employer
) -> list[RawPosting]:
    postings: list[RawPosting] = []
    total: int | None = None

    for page in range(_MAX_PAGES):
        payload = _post_page(client, url, page * _PAGE_SIZE, employer)
        if total is None:
            total = _read_total(payload, employer)
        page_jobs = payload["jobPostings"]
        for job in page_jobs:
            if not isinstance(job, dict):
                raise FetchError(f"workday job entry for {employer.name!r} is not an object")
            postings.append(_map_job(job, base, site, employer))
        if not page_jobs or len(postings) >= total:
            break

    # Completeness guard: a short tally means a truncated fetch — fail loudly rather than
    # return a partial list the diff would read as mass closures.
    if total is not None and len(postings) < total:
        raise FetchError(
            f"workday fetch for {employer.name!r} incomplete: got {len(postings)} of {total}"
        )
    return postings


def _post_page(client: httpx.Client, url: str, offset: int, employer: Employer) -> dict[str, Any]:
    body = {"appliedFacets": {}, "limit": _PAGE_SIZE, "offset": offset, "searchText": ""}
    try:
        response = client.post(url, json=body)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise FetchError(
            f"workday fetch failed for {employer.name!r} (offset {offset}): {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise FetchError(f"workday returned non-JSON for {employer.name!r}: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("jobPostings"), list):
        raise FetchError(f"workday response for {employer.name!r} missing a 'jobPostings' list")
    return payload


def _read_total(payload: dict[str, Any], employer: Employer) -> int:
    total = payload.get("total")
    if not isinstance(total, int):
        raise FetchError(f"workday response for {employer.name!r} missing an integer 'total'")
    return total


def _board_base_and_site(cxs_url: str, employer: Employer) -> tuple[str, str]:
    """Split a cxs URL into the public board base + site.

    `https://{host}/wday/cxs/{tenant}/{site}/jobs` → (`https://{host}`, `{site}`), so an apply URL
    is `{base}/{site}{externalPath}`.
    """
    base, sep, rest = cxs_url.partition("/wday/cxs/")
    segments = rest.strip("/").split("/")
    if not sep or len(segments) < 3:
        raise FetchError(f"workday endpoint for {employer.name!r} is not a cxs URL: {cxs_url!r}")
    return base, segments[1]


def _map_job(job: dict[str, Any], base: str, site: str, employer: Employer) -> RawPosting:
    """Map one Workday jobPosting to a `RawPosting`; raise `FetchError` on a missing field."""
    external_path = job.get("externalPath")
    title = job.get("title")
    if not isinstance(external_path, str) or not external_path:
        raise FetchError(f"workday job for {employer.name!r} missing 'externalPath'")
    if not isinstance(title, str) or not title:
        raise FetchError(f"workday job for {employer.name!r} missing 'title'")

    return RawPosting(
        external_id=external_path,
        title=title,
        apply_url=f"{base}/{site}{external_path}",
        location=job.get("locationsText"),
        updated_at=None,  # Workday's list gives only a relative `postedOn` string
        raw=job,
        description=None,  # list-only; the description is a lazy Layer-2 fetch
    )
