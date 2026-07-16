"""iCIMS (Jibe Career Sites) Layer-1 fetcher (`docs/05`, `docs/07`).

iCIMS ships two front-ends. The legacy ``careers-{tenant}.icims.com`` portal is a
frame-busted SPA with no clean JSON, but the modern **iCIMS Career Sites** product
(formerly Jibe) exposes a clean, unauthenticated JSON jobs API on the employer's own
careers domain. The seed `endpoint` column is authoritative and points at it:

``GET {careers_base}/api/jobs?page={n}&limit={N}`` →
``{"jobs": [{"data": {...}}], "totalCount": int, ...}``.

One generic fetcher covers every Jibe tenant — the payload shape is uniform across
employers (verified live against Garmin, Constellation, Exelon, SIG, ICE, SITA — D-019),
so this is a per-platform fetcher, never a per-company scraper (D-017/D-004). Legacy-portal
or non-Jibe tenants (e.g. Joby, Alaska) have no clean API and route to Layer 2 instead.

Two contracts, mirroring Workday (`docs/07`, the false-closure guard in `docs/08`):

- **Paginate fully or fail.** ``totalCount`` drives pagination; we page until we have
  collected it. Any page error raises `FetchError` and we return nothing; a short final
  tally is also a hard failure — a truncated list would read as mass closures.
- Unlike Workday, the Jibe payload is **rich**: ``apply_url``, full ``description`` text,
  and a real ISO ``update_date`` are all in the list response, so there is no lazy
  Layer-2 detail fetch and ``updated_at`` is populated (a freshness win for D-030).

Mapping (`docs/05`): ``external_id = req_id`` (the ATS requisition id — stable, unique, the
diff key D-016), ``apply_url`` (given directly), ``title``, ``location = full_location``,
``updated_at = update_date``. ``description`` joins the overview + responsibilities +
qualifications so Layer-2 extraction reasons over the full posting.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from vja.fetchers.base import FetchError
from vja.fetchers.endpoints import build_endpoint
from vja.models import AtsType, Employer, RawPosting

_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"
_TIMEOUT = 30.0
_PAGE_SIZE = 100  # the Jibe API honours an explicit limit; 100 keeps requests few + polite
_MAX_PAGES = 200  # safety cap against a bad `totalCount` (200×100 = 20000, far above any tenant)

# The free-text fields, in order, whose join gives Layer-2 the full posting body.
_DESCRIPTION_FIELDS = ("description", "responsibilities", "qualifications")


class IcimsFetcher:
    """Fetches open postings from an iCIMS Career Sites (Jibe) board. Pure read (`docs/05`).

    A `client` may be injected (tests / connection reuse); otherwise a short-lived one is created
    per fetch with an identifiable User-Agent (politeness — `docs/05`).
    """

    ats_type: AtsType = AtsType.ICIMS

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, employer: Employer) -> list[RawPosting]:
        url = build_endpoint(employer)
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            return _paginate(client, url, employer)
        finally:
            if self._client is None:
                client.close()


def _paginate(client: httpx.Client, url: str, employer: Employer) -> list[RawPosting]:
    postings: list[RawPosting] = []
    total: int | None = None

    for page in range(1, _MAX_PAGES + 1):
        payload = _get_page(client, url, page, employer)
        page_total = _read_total(payload, employer)
        if total is None:
            total = page_total
        elif page_total != total:
            raise FetchError(
                f"icims total changed during fetch for {employer.name!r}: {total} → {page_total}"
            )
        page_jobs = payload["jobs"]
        for job in page_jobs:
            postings.append(_map_job(job, employer))
        if not page_jobs or len(postings) >= total:
            break

    # Completeness guard: only an exact tally is safe. Both a short and an over-counted snapshot
    # can hide pagination drift that the diff would otherwise interpret as real board churn.
    if total is None or len(postings) != total:
        expected = total if total is not None else "unknown"
        raise FetchError(
            f"icims fetch for {employer.name!r} incomplete: got {len(postings)} of {expected}"
        )
    return postings


def _get_page(client: httpx.Client, url: str, page: int, employer: Employer) -> dict[str, Any]:
    try:
        response = client.get(url, params={"page": page, "limit": _PAGE_SIZE})
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise FetchError(f"icims fetch failed for {employer.name!r} (page {page}): {exc}") from exc
    except json.JSONDecodeError as exc:
        raise FetchError(f"icims returned non-JSON for {employer.name!r}: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise FetchError(f"icims response for {employer.name!r} missing a 'jobs' list")
    return payload


def _read_total(payload: dict[str, Any], employer: Employer) -> int:
    total = payload.get("totalCount")
    if not isinstance(total, int):
        raise FetchError(f"icims response for {employer.name!r} missing an integer 'totalCount'")
    return total


def _map_job(job: dict[str, Any], employer: Employer) -> RawPosting:
    """Map one Jibe job entry to a `RawPosting`; raise `FetchError` on a missing required field."""
    if not isinstance(job, dict) or not isinstance(job.get("data"), dict):
        raise FetchError(f"icims job entry for {employer.name!r} missing a 'data' object")
    data = job["data"]

    req_id = data.get("req_id")
    title = data.get("title")
    apply_url = data.get("apply_url")
    if req_id in (None, ""):
        raise FetchError(f"icims job for {employer.name!r} missing 'req_id'")
    if not isinstance(title, str) or not title:
        raise FetchError(f"icims job for {employer.name!r} missing 'title'")
    if not isinstance(apply_url, str) or not apply_url:
        raise FetchError(f"icims job for {employer.name!r} missing 'apply_url'")

    updated_at = data.get("update_date") or data.get("posted_date")
    return RawPosting(
        external_id=str(req_id),
        title=title,
        apply_url=apply_url,
        location=data.get("full_location") or data.get("location_name"),
        updated_at=updated_at if isinstance(updated_at, str) else None,
        raw=data,
        description=_join_description(data),
    )


def _join_description(data: dict[str, Any]) -> str | None:
    """Join the overview + responsibilities + qualifications into one body for Layer 2."""
    parts = [data[f] for f in _DESCRIPTION_FIELDS if isinstance(data.get(f), str) and data[f]]
    return "\n\n".join(parts) if parts else None
