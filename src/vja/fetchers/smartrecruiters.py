"""SmartRecruiters Layer-1 fetcher (`docs/05`, `docs/07`).

SmartRecruiters exposes a clean, unauthenticated **public postings API** on a uniform host —
the same shape for every tenant, so this is one generic per-platform fetcher, never a
per-company scraper (D-017/D-004). The seed `endpoint` is derived from the slug
(`endpoints.py`), like Greenhouse/Lever/Ashby/Workable:

``GET https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit={N}&offset={M}`` →
``{"offset": int, "limit": int, "totalFound": int, "content": [ {...} ]}``.

The contract mirrors **Workday** (`docs/07`): list-only + paginate-or-fail + a lazy detail fetch.

- **List-only.** The postings list carries the title, location, level, and `releasedDate`, but
  **no job description and no apply URL**. The public apply URL is *constructed*
  (``https://jobs.smartrecruiters.com/{slug}/{id}`` — verified to resolve), so the apply link
  needs no detail fetch (D-008). The description lives only on the per-posting detail endpoint
  and is fetched lazily, per in-scope survivor, by Layer-2 extraction (`extract.py`) via
  `fetch_detail` — the cost-disciplined path (D-035), exactly like Workday.
- **Paginate fully or fail.** ``totalFound`` drives pagination; a short final tally is a hard
  `FetchError` (a truncated list would read as mass closures — the false-closure guard, `docs/08`).

Mapping (`docs/05`): ``external_id = id`` (SmartRecruiters' stable posting id, the diff key D-016),
``apply_url`` constructed from slug + id, ``title = name``, ``location`` from the ``fullLocation``
(empty comma-segments collapsed; the full country name feeds the Stage-B US signal better than the
bare ISO ``country``), ``updated_at = releasedDate`` (a D-030 freshness win). ``description = None``
(lazy — see `fetch_detail`).
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
_PAGE_SIZE = 100  # the API honours an explicit limit; 100 keeps requests few + polite
_MAX_PAGES = 200  # safety cap against a bad `totalFound` (200×100 = 20000, far above any tenant)

# The public posting page (the apply link), constructed from the slug + posting id. The list omits
# any apply URL; this is the canonical short form and redirects to the slugged page (D-008).
_APPLY_URL = "https://jobs.smartrecruiters.com/{slug}/{external_id}"


class SmartRecruitersFetcher:
    """Fetches open postings from a SmartRecruiters company board. Pure read (`docs/05`).

    A `client` may be injected (tests / connection reuse); otherwise a short-lived one is created
    per fetch with an identifiable User-Agent (politeness — `docs/05`).
    """

    ats_type: AtsType = AtsType.SMARTRECRUITERS

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

    def fetch_detail(self, employer: Employer, external_id: str) -> dict[str, Any]:
        """Fetch one posting's full detail — the Layer-2 description (`jobAd.sections`).

        The list omits the description; the detail endpoint is the list URL + ``/{id}`` and returns
        the full posting object (``jobAd.sections`` has the company/job/quals HTML). Returns
        the whole dict for extraction; raises `FetchError` on failure.
        """
        detail_url = f"{build_endpoint(employer)}/{external_id}"
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            response = client.get(detail_url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise FetchError(
                f"smartrecruiters detail fetch failed for {employer.name!r}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise FetchError(
                f"smartrecruiters detail non-JSON for {employer.name!r}: {exc}"
            ) from exc
        finally:
            if self._client is None:
                client.close()

        if not isinstance(payload, dict):
            raise FetchError(f"smartrecruiters detail for {employer.name!r} is not an object")
        return payload


def _paginate(client: httpx.Client, url: str, employer: Employer) -> list[RawPosting]:
    postings: list[RawPosting] = []
    total: int | None = None

    for page in range(_MAX_PAGES):
        payload = _get_page(client, url, page * _PAGE_SIZE, employer)
        if total is None:
            total = _read_total(payload, employer)
        page_jobs = payload["content"]
        for job in page_jobs:
            postings.append(_map_job(job, employer))
        if not page_jobs or len(postings) >= total:
            break

    # Completeness guard: a short tally means a truncated fetch — fail loudly rather than return a
    # partial list the diff would read as mass closures.
    if total is not None and len(postings) < total:
        raise FetchError(
            f"smartrecruiters fetch for {employer.name!r} incomplete: {len(postings)} of {total}"
        )
    return postings


def _get_page(client: httpx.Client, url: str, offset: int, employer: Employer) -> dict[str, Any]:
    try:
        response = client.get(url, params={"limit": _PAGE_SIZE, "offset": offset})
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise FetchError(
            f"smartrecruiters fetch failed for {employer.name!r} (offset {offset}): {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise FetchError(f"smartrecruiters returned non-JSON for {employer.name!r}: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("content"), list):
        raise FetchError(f"smartrecruiters response for {employer.name!r} missing a 'content' list")
    return payload


def _read_total(payload: dict[str, Any], employer: Employer) -> int:
    total = payload.get("totalFound")
    if not isinstance(total, int):
        raise FetchError(f"smartrecruiters response for {employer.name!r} missing 'totalFound'")
    return total


def _map_job(job: dict[str, Any], employer: Employer) -> RawPosting:
    """Map one SmartRecruiters posting to a `RawPosting`; raise `FetchError` on a missing field."""
    if not isinstance(job, dict):
        raise FetchError(f"smartrecruiters posting for {employer.name!r} is not an object")
    external_id = job.get("id")
    title = job.get("name")
    if external_id in (None, ""):
        raise FetchError(f"smartrecruiters posting for {employer.name!r} missing 'id'")
    if not isinstance(title, str) or not title:
        raise FetchError(f"smartrecruiters posting for {employer.name!r} missing 'name'")

    return RawPosting(
        external_id=str(external_id),
        title=title,
        apply_url=_APPLY_URL.format(slug=employer.ats_slug, external_id=external_id),
        location=_location(job),
        updated_at=_updated_at(job),
        raw=job,
        description=None,  # list-only; the description is a lazy Layer-2 fetch (`fetch_detail`)
    )


def _location(job: dict[str, Any]) -> str | None:
    """Readable location from ``location.fullLocation``, collapsing empty comma-segments.

    ``fullLocation`` is e.g. "Houston, TX, United States" but "Singapore, , Singapore" when the
    region is blank — keep only the non-empty parts."""
    loc = job.get("location")
    full = loc.get("fullLocation") if isinstance(loc, dict) else None
    if not isinstance(full, str) or not full:
        return None
    parts = [p.strip() for p in full.split(",") if p.strip()]
    return ", ".join(parts) if parts else None


def _updated_at(job: dict[str, Any]) -> str | None:
    released = job.get("releasedDate")
    return released if isinstance(released, str) and released else None
