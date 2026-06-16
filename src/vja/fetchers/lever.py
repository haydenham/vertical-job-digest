"""Lever Layer-1 fetcher (`docs/05`).

Endpoint: ``GET https://api.lever.co/v0/postings/{slug}?mode=json`` — returns a JSON
**array** (no wrapper object). Mapping: ``external_id = id``, ``title = text``,
``apply_url = applyUrl or hostedUrl``, ``location = categories.location``. The whole
job dict is kept as `raw`.
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


class LeverFetcher:
    """Fetches open postings from a Lever job board. Pure read (`docs/05`)."""

    ats_type: AtsType = AtsType.LEVER

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
            raise FetchError(f"lever fetch failed for {employer.name!r}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FetchError(f"lever returned non-JSON for {employer.name!r}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        if not isinstance(payload, list):
            raise FetchError(f"lever response for {employer.name!r} is not a JSON array")

        postings: list[RawPosting] = []
        for job in payload:
            if not isinstance(job, dict):
                raise FetchError(f"lever job entry for {employer.name!r} is not an object")
            postings.append(_map_job(job, employer))
        return postings


def _map_job(job: dict[str, Any], employer: Employer) -> RawPosting:
    """Map one Lever posting to a `RawPosting`. Raises `FetchError` on a missing
    required field (`id`, `text`, and an apply link)."""
    try:
        external_id = str(job["id"])
        title = job["text"]
    except KeyError as exc:
        raise FetchError(f"lever job for {employer.name!r} missing required field {exc}") from exc

    apply_url = job.get("applyUrl") or job.get("hostedUrl")
    if not apply_url:
        raise FetchError(f"lever job {external_id} for {employer.name!r} has no apply/hosted URL")

    categories = job.get("categories")
    location = categories.get("location") if isinstance(categories, dict) else None

    # Lever's createdAt is epoch-millis (int); RawPosting.updated_at is a string.
    created_at = job.get("createdAt")
    updated_at = str(created_at) if created_at is not None else None

    # Prefer the plain-text description; some postings only populate the HTML `description`.
    description = job.get("descriptionPlain") or job.get("description")

    return RawPosting(
        external_id=external_id,
        title=title,
        apply_url=apply_url,
        location=location,
        updated_at=updated_at,
        raw=job,
        description=description,
    )
