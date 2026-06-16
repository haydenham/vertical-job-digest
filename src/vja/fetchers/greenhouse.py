"""Greenhouse Layer-1 fetcher (`docs/05`).

Endpoint: ``GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true``
(``?content=true`` returns the description inline, feeding `content_hash` + Layer 2
without a second request). Mapping (`docs/05`):
``external_id = str(id)``, ``title``, ``apply_url = absolute_url``,
``location = location.name``, ``updated_at``. The whole job dict is kept as `raw`.
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


class GreenhouseFetcher:
    """Fetches open postings from a Greenhouse job board. Pure read (`docs/05`).

    A `client` may be injected (for tests / connection reuse); otherwise a short-lived
    one is created per fetch with an identifiable User-Agent (politeness — `docs/05`).
    """

    ats_type: AtsType = AtsType.GREENHOUSE

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
            raise FetchError(f"greenhouse fetch failed for {employer.name!r}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FetchError(f"greenhouse returned non-JSON for {employer.name!r}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise FetchError(f"greenhouse response for {employer.name!r} missing a 'jobs' list")

        postings: list[RawPosting] = []
        for job in payload["jobs"]:
            if not isinstance(job, dict):
                raise FetchError(f"greenhouse job entry for {employer.name!r} is not an object")
            postings.append(_map_job(job, employer))
        return postings


def _map_job(job: dict[str, Any], employer: Employer) -> RawPosting:
    """Map one Greenhouse job dict to a `RawPosting`. Raises `FetchError` if a
    required field (`id`, `title`, `absolute_url`) is missing — silent garbage is
    worse than a loud failure."""
    try:
        external_id = str(job["id"])
        title = job["title"]
        apply_url = job["absolute_url"]
    except KeyError as exc:
        raise FetchError(
            f"greenhouse job for {employer.name!r} missing required field {exc}"
        ) from exc

    location_obj = job.get("location")
    location = location_obj.get("name") if isinstance(location_obj, dict) else None

    return RawPosting(
        external_id=external_id,
        title=title,
        apply_url=apply_url,
        location=location,
        updated_at=job.get("updated_at"),
        raw=job,
        # `?content=true` returns the description inline as HTML.
        description=job.get("content"),
    )
