"""Ashby Layer-1 fetcher (`docs/05`).

Endpoint: ``GET https://api.ashbyhq.com/posting-api/job-board/{slug}`` — returns
``{"jobs": [...]}``. Mapping: ``external_id = id``, ``title = title``,
``apply_url = applyUrl or jobUrl``, ``location = location``. The whole job dict is
kept as `raw`.
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


class AshbyFetcher:
    """Fetches open postings from an Ashby job board. Pure read (`docs/05`)."""

    ats_type: AtsType = AtsType.ASHBY

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, employer: Employer) -> list[RawPosting]:
        url = build_endpoint(employer)
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise FetchError(f"ashby fetch failed for {employer.name!r}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FetchError(f"ashby returned non-JSON for {employer.name!r}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise FetchError(f"ashby response for {employer.name!r} missing a 'jobs' list")

        postings: list[RawPosting] = []
        for job in payload["jobs"]:
            if not isinstance(job, dict):
                raise FetchError(f"ashby job entry for {employer.name!r} is not an object")
            postings.append(_map_job(job, employer))
        return postings


def _map_job(job: dict[str, Any], employer: Employer) -> RawPosting:
    """Map one Ashby posting to a `RawPosting`. Raises `FetchError` on a missing
    required field (`id`, `title`, and an apply link)."""
    try:
        external_id = str(job["id"])
        title = job["title"]
    except KeyError as exc:
        raise FetchError(f"ashby job for {employer.name!r} missing required field {exc}") from exc

    apply_url = job.get("applyUrl") or job.get("jobUrl")
    if not apply_url:
        raise FetchError(f"ashby job {external_id} for {employer.name!r} has no apply/job URL")

    location = job.get("location")
    if not isinstance(location, str):
        location = None

    # Prefer the plain-text description; fall back to the HTML variant.
    description = job.get("descriptionPlain") or job.get("descriptionHtml")

    return RawPosting(
        external_id=external_id,
        title=title,
        apply_url=apply_url,
        location=location,
        updated_at=job.get("publishedAt"),
        raw=job,
        description=description,
    )
