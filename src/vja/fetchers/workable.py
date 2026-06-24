"""Workable Layer-1 fetcher (`docs/05`, `docs/07`).

Workable exposes a clean, unauthenticated **embed-widget JSON API** on its own host —
the same shape for every tenant, so this is one generic per-platform fetcher, never a
per-company scraper (D-017/D-004). The seed `endpoint` is derived from the slug
(`endpoints.py`), exactly like Greenhouse/Lever/Ashby:

``GET https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true`` →
``{"name": str, "description": str, "jobs": [ {...} ]}``.

Two things make it simpler than iCIMS/Workday:

- **Single response, not paginated.** The widget returns *all* currently-open jobs in one
  ``jobs`` array (no ``total``/offset), so — like Greenhouse/Lever/Ashby — there is no
  paginate-or-fail loop. The false-closure guard (`docs/08`) is the single-request contract:
  any transport/parse/shape error raises `FetchError` (never a partial list); a clean 200 is
  the authoritative complete set, and an empty ``jobs`` array is a legitimate "0 open".
- **Rich list.** ``?details=true`` includes the full ``description`` HTML, so there is no
  lazy Layer-2 detail fetch and ``updated_at`` is populated (a D-030 freshness win).

Mapping (`docs/05`): ``external_id = shortcode`` (Workable's stable requisition id, the diff
key D-016), ``apply_url = url`` (the public posting page), ``title``, ``location`` joined from
``city``/``state``/``country``, ``updated_at = published_on``, ``description`` (HTML).
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

# The location parts, in order, whose comma-join gives a human-readable L1 location string
# (e.g. "Houston, Texas, United States"). The full `country`/`state` names feed the Stage-B
# US-signal prefilter (D-036) better than the bare ISO codes in `locations[]`.
_LOCATION_FIELDS = ("city", "state", "country")


class WorkableFetcher:
    """Fetches open postings from a Workable embed-widget board. Pure read (`docs/05`).

    A `client` may be injected (tests / connection reuse); otherwise a short-lived one is
    created per fetch with an identifiable User-Agent (politeness — `docs/05`).
    """

    ats_type: AtsType = AtsType.WORKABLE

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
            raise FetchError(f"workable fetch failed for {employer.name!r}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FetchError(f"workable returned non-JSON for {employer.name!r}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise FetchError(f"workable response for {employer.name!r} missing a 'jobs' list")

        postings: list[RawPosting] = []
        for job in payload["jobs"]:
            if not isinstance(job, dict):
                raise FetchError(f"workable job entry for {employer.name!r} is not an object")
            postings.append(_map_job(job, employer))
        return postings


def _map_job(job: dict[str, Any], employer: Employer) -> RawPosting:
    """Map one Workable job dict to a `RawPosting`. Raises `FetchError` if a required
    field (`shortcode`, `title`, `url`) is missing — silent garbage is worse than a loud
    failure."""
    try:
        external_id = str(job["shortcode"])
        title = job["title"]
        apply_url = job["url"]
    except KeyError as exc:
        raise FetchError(
            f"workable job for {employer.name!r} missing required field {exc}"
        ) from exc
    if not external_id or not title or not apply_url:
        raise FetchError(f"workable job for {employer.name!r} has an empty required field")

    updated_at = job.get("published_on") or job.get("created_at")
    return RawPosting(
        external_id=external_id,
        title=title,
        apply_url=apply_url,
        location=_join_location(job),
        updated_at=updated_at if isinstance(updated_at, str) and updated_at else None,
        raw=job,
        # `?details=true` returns the description inline as HTML.
        description=job.get("description"),
    )


def _join_location(job: dict[str, Any]) -> str | None:
    """Join city/state/country into one location string (e.g. "Houston, Texas, United States")."""
    parts = [job[f] for f in _LOCATION_FIELDS if isinstance(job.get(f), str) and job[f]]
    return ", ".join(parts) if parts else None
