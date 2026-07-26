"""Paylocity Recruiting Layer-1 fetcher (D-076).

Paylocity's public tenant listing is server-rendered HTML containing one complete
``window.pageData`` JSON object. The ``Jobs`` array is authoritative and unpaginated;
any transport/shape/parse failure raises ``FetchError`` so a partial result can never
look like mass closures. List rows omit descriptions, which are fetched lazily from the
public detail page for in-scope postings only.

The per-tenant endpoint is explicit because it embeds both the employer UUID and display
slug: ``.../Recruiting/jobs/All/{uuid}/{name}``. ``external_id = JobId`` (D-016), and
the public apply URL is the stable ``/Recruiting/jobs/Apply/{JobId}`` route.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from vja.fetchers.base import FetchError, joined_body
from vja.fetchers.endpoints import build_endpoint
from vja.models import AtsType, Employer, RawPosting

_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"
_TIMEOUT = 30.0
_PAGE_DATA = re.compile(r"window\.pageData\s*=\s*(\{.*?\})\s*;", re.DOTALL)
_DETAIL_HEADER = "Description"


class PaylocityFetcher:
    """Fetch all jobs from one explicit Paylocity Recruiting tenant endpoint."""

    ats_type: AtsType = AtsType.PAYLOCITY

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, employer: Employer) -> list[RawPosting]:
        url = build_endpoint(employer)
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise FetchError(f"paylocity fetch failed for {employer.name!r}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        payload = _parse_page_data(response.text, employer)
        jobs = payload.get("Jobs")
        if not isinstance(jobs, list):
            raise FetchError(f"paylocity response for {employer.name!r} missing a 'Jobs' list")
        return [_map_job(job, employer, url) for job in jobs]

    def fetch_detail(self, employer: Employer, external_id: str) -> dict[str, str | None]:
        """Fetch the public detail page and return its description text."""
        list_url = build_endpoint(employer)
        detail_url = f"{_origin(list_url)}/Recruiting/jobs/Details/{external_id}"
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            response = client.get(detail_url, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise FetchError(f"paylocity detail fetch failed for {employer.name!r}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        soup = BeautifulSoup(response.text, "html.parser")
        header = next(
            (
                node
                for node in soup.select(".job-listing-header")
                if node.get_text(strip=True) == _DETAIL_HEADER
            ),
            None,
        )
        description = header.find_next_sibling("div") if header is not None else None
        if description is None:
            raise FetchError(f"paylocity detail for {employer.name!r} has no description section")
        return {"description": description.get_text(" ", strip=True), "url": detail_url}

    def detail_description(self, payload: dict[str, Any]) -> str | None:
        """The posting body out of a `fetch_detail` payload — already flattened to text above."""
        return joined_body(payload.get("description"))


def _parse_page_data(html: str, employer: Employer) -> dict[str, Any]:
    match = _PAGE_DATA.search(html)
    if match is None:
        raise FetchError(f"paylocity response for {employer.name!r} has no window.pageData")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise FetchError(
            f"paylocity pageData for {employer.name!r} is invalid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise FetchError(f"paylocity pageData for {employer.name!r} is not an object")
    return payload


def _map_job(job: Any, employer: Employer, list_url: str) -> RawPosting:
    if not isinstance(job, dict):
        raise FetchError(f"paylocity job entry for {employer.name!r} is not an object")
    try:
        raw_id = job["JobId"]
        title = job["JobTitle"]
    except KeyError as exc:
        raise FetchError(
            f"paylocity job for {employer.name!r} missing required field {exc}"
        ) from exc
    if (
        isinstance(raw_id, bool)
        or not isinstance(raw_id, (int, str))
        or not str(raw_id)
        or not isinstance(title, str)
        or not title
    ):
        raise FetchError(f"paylocity job for {employer.name!r} has an empty required field")
    external_id = str(raw_id)

    origin = _origin(list_url)
    return RawPosting(
        external_id=external_id,
        title=title,
        apply_url=f"{origin}/Recruiting/jobs/Apply/{external_id}",
        location=_location(job),
        updated_at=_nonempty_string(job.get("PublishedDate")),
        raw=job,
        description=None,
    )


def _location(job: dict[str, Any]) -> str | None:
    location = _nonempty_string(job.get("LocationName"))
    if location:
        return location
    nested = job.get("JobLocation")
    if isinstance(nested, dict):
        for field in ("Name", "Metro", "City", "State", "Country"):
            value = _nonempty_string(nested.get(field))
            if value:
                return value
    return "Remote" if job.get("IsRemote") is True else None


def _nonempty_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
