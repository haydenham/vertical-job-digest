"""Phenom Career Connect Layer-1 fetcher (D-076).

Phenom career sites expose a common public ``POST /widgets`` API. ``refineSearch``
returns list-only jobs and a ``totalHits`` completeness anchor; ``jobDetail`` lazily
returns the full description for in-scope survivors. Per-tenant ``lang`` and ``country``
values live in the employer endpoint query, never in provider or company-specific code:
``https://tenant.example?lang=en_us&country=us``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx

from vja.fetchers.base import FetchError
from vja.fetchers.endpoints import build_endpoint
from vja.models import AtsType, Employer, RawPosting

_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"
_TIMEOUT = 30.0
_PAGE_SIZE = 100
_MAX_PAGES = 200


@dataclass(frozen=True)
class _TenantConfig:
    widget_url: str
    lang: str
    country: str


class PhenomFetcher:
    """Fetch all open postings from one configured Phenom Career Connect tenant."""

    ats_type: AtsType = AtsType.PHENOM

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, employer: Employer) -> list[RawPosting]:
        config = _tenant_config(employer)
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            return _paginate(client, config, employer)
        finally:
            if self._client is None:
                client.close()

    def fetch_detail(self, employer: Employer, external_id: str) -> dict[str, Any]:
        """Fetch one full ``jobDetail`` object using the stable list ``jobId``."""
        config = _tenant_config(employer)
        body = _common_body(config) | {
            "pageName": "job",
            "ddoKey": "jobDetail",
            "jobSeqNo": external_id,
        }
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            payload = _post(client, config.widget_url, body, employer, "detail")
        finally:
            if self._client is None:
                client.close()

        section = _section(payload, "jobDetail", employer)
        data = section.get("data")
        job = data.get("job") if isinstance(data, dict) else None
        if (
            not isinstance(job, dict)
            or not isinstance(job.get("description"), str)
            or not job["description"]
        ):
            raise FetchError(f"phenom detail for {employer.name!r} missing job description")
        return job


def _paginate(client: httpx.Client, config: _TenantConfig, employer: Employer) -> list[RawPosting]:
    postings: list[RawPosting] = []
    total: int | None = None
    offset = 0

    for _page in range(_MAX_PAGES):
        body = _common_body(config) | {
            "pageName": "search-results",
            "ddoKey": "refineSearch",
            "from": offset,
            "jobs": True,
            "counts": True,
            "size": _PAGE_SIZE,
        }
        payload = _post(client, config.widget_url, body, employer, "list")
        section = _section(payload, "refineSearch", employer)
        page_total = section.get("totalHits")
        if not isinstance(page_total, int) or isinstance(page_total, bool) or page_total < 0:
            raise FetchError(f"phenom response for {employer.name!r} has no valid totalHits")
        if total is None:
            total = page_total
        elif page_total != total:
            raise FetchError(
                f"phenom total changed during fetch for {employer.name!r}: {total} → {page_total}"
            )

        data = section.get("data")
        jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs, list):
            raise FetchError(f"phenom response for {employer.name!r} missing a jobs list")
        for job in jobs:
            postings.append(_map_job(job, employer))
        if len(postings) >= total or not jobs:
            break
        offset += len(jobs)

    if total is None or len(postings) != total:
        expected = total if total is not None else "unknown"
        raise FetchError(
            f"phenom fetch for {employer.name!r} incomplete: {len(postings)} of {expected}"
        )
    if len({posting.external_id for posting in postings}) != len(postings):
        raise FetchError(f"phenom fetch for {employer.name!r} returned duplicate job ids")
    return postings


def _map_job(job: Any, employer: Employer) -> RawPosting:
    if not isinstance(job, dict):
        raise FetchError(f"phenom job entry for {employer.name!r} is not an object")
    try:
        external_id = job["jobId"]
        title = job["title"]
        apply_url = job["applyUrl"]
    except KeyError as exc:
        raise FetchError(f"phenom job for {employer.name!r} missing required field {exc}") from exc
    if not all(isinstance(value, str) and value for value in (external_id, title, apply_url)):
        raise FetchError(f"phenom job for {employer.name!r} has an empty required field")
    return RawPosting(
        external_id=external_id,
        title=title,
        apply_url=apply_url,
        location=_string(job.get("location")) or _string(job.get("cityStateCountry")),
        updated_at=_string(job.get("postedDate")),
        raw=job,
        description=None,
    )


def _tenant_config(employer: Employer) -> _TenantConfig:
    endpoint = build_endpoint(employer)
    parts = urlsplit(endpoint)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"phenom employer {employer.name!r} has an invalid endpoint")
    query = parse_qs(parts.query, keep_blank_values=True)
    lang = _one_query_value(query, "lang", employer)
    country = _one_query_value(query, "country", employer)
    base = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", "")).rstrip("/")
    return _TenantConfig(widget_url=f"{base}/widgets", lang=lang, country=country)


def _one_query_value(query: dict[str, list[str]], key: str, employer: Employer) -> str:
    values = query.get(key)
    if values is None or len(values) != 1 or not values[0]:
        raise ValueError(
            f"phenom employer {employer.name!r} endpoint requires one non-empty {key!r} query value"
        )
    return values[0]


def _common_body(config: _TenantConfig) -> dict[str, Any]:
    return {
        "lang": config.lang,
        "deviceType": "desktop",
        "country": config.country,
    }


def _post(
    client: httpx.Client,
    url: str,
    body: dict[str, Any],
    employer: Employer,
    operation: str,
) -> dict[str, Any]:
    try:
        response = client.post(url, json=body)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise FetchError(f"phenom {operation} fetch failed for {employer.name!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise FetchError(
            f"phenom {operation} returned non-JSON for {employer.name!r}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise FetchError(f"phenom {operation} response for {employer.name!r} is not an object")
    return payload


def _section(payload: dict[str, Any], key: str, employer: Employer) -> dict[str, Any]:
    section = payload.get(key)
    if not isinstance(section, dict) or section.get("status") != 200:
        raise FetchError(f"phenom response for {employer.name!r} missing successful {key!r}")
    return section


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
