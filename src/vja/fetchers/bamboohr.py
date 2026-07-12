"""Generic BambooHR Layer-1 list fetcher and lazy detail resolver."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from vja.fetchers.base import FetchError
from vja.fetchers.endpoints import build_endpoint
from vja.models import AtsType, Employer, RawPosting

_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"
_TIMEOUT = 30.0


class BambooHRFetcher:
    """Fetch the authoritative job list for one slug-derived BambooHR board."""

    ats_type: AtsType = AtsType.BAMBOOHR

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, employer: Employer) -> list[RawPosting]:
        list_url = build_endpoint(employer)
        payload = self._get_json(list_url, employer, "list")
        meta = payload.get("meta")
        if not isinstance(meta, dict):
            raise FetchError(f"bamboohr response for {employer.name!r} missing a meta object")
        total = meta.get("totalCount")
        if not isinstance(total, int) or isinstance(total, bool) or total < 0:
            raise FetchError(f"bamboohr response for {employer.name!r} has no valid totalCount")
        jobs = payload.get("result")
        if not isinstance(jobs, list):
            raise FetchError(f"bamboohr response for {employer.name!r} missing a result list")
        if len(jobs) != total:
            raise FetchError(
                f"bamboohr fetch for {employer.name!r} incomplete: {len(jobs)} of {total}"
            )
        postings = [_map_job(job, employer, list_url) for job in jobs]
        if len({posting.external_id for posting in postings}) != len(postings):
            raise FetchError(f"bamboohr fetch for {employer.name!r} returned duplicate job ids")
        return postings

    def fetch_detail(self, employer: Employer, external_id: str) -> dict[str, Any]:
        """Return only ``result.jobOpening``; never expose application form fields."""
        list_url = build_endpoint(employer)
        detail_url = f"{_origin(list_url)}/careers/{quote(external_id, safe='')}/detail"
        payload = self._get_json(detail_url, employer, "detail")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise FetchError(f"bamboohr detail for {employer.name!r} missing a result object")
        job = result.get("jobOpening")
        if not isinstance(job, dict):
            raise FetchError(f"bamboohr detail for {employer.name!r} missing a jobOpening object")
        description = job.get("description")
        if not isinstance(description, str) or not description.strip():
            raise FetchError(f"bamboohr detail for {employer.name!r} missing job description")
        return job

    def _get_json(self, url: str, employer: Employer, operation: str) -> dict[str, Any]:
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise FetchError(
                f"bamboohr {operation} fetch failed for {employer.name!r}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise FetchError(
                f"bamboohr {operation} returned non-JSON for {employer.name!r}: {exc}"
            ) from exc
        finally:
            if self._client is None:
                client.close()
        if not isinstance(payload, dict):
            raise FetchError(
                f"bamboohr {operation} response for {employer.name!r} is not an object"
            )
        return payload


def _map_job(job: Any, employer: Employer, list_url: str) -> RawPosting:
    if not isinstance(job, dict):
        raise FetchError(f"bamboohr job entry for {employer.name!r} is not an object")
    try:
        raw_id = job["id"]
        raw_title = job["jobOpeningName"]
    except KeyError as exc:
        raise FetchError(
            f"bamboohr job for {employer.name!r} missing required field {exc}"
        ) from exc
    if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
        raise FetchError(f"bamboohr job for {employer.name!r} has an empty required field")
    external_id = str(raw_id).strip()
    title = raw_title.strip() if isinstance(raw_title, str) else ""
    if not external_id or not title:
        raise FetchError(f"bamboohr job for {employer.name!r} has an empty required field")
    return RawPosting(
        external_id=external_id,
        title=title,
        apply_url=f"{_origin(list_url)}/careers/{quote(external_id, safe='')}",
        location=_location(job),
        updated_at=None,
        raw=job,
        description=None,
    )


def _location(job: dict[str, Any]) -> str | None:
    ats_location = job.get("atsLocation")
    if isinstance(ats_location, dict):
        value = _join_location(ats_location)
        if value:
            return value
    fallback = job.get("location")
    if isinstance(fallback, dict):
        value = _join_location(fallback)
        if value:
            return value
    elif isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return "Remote" if job.get("isRemote") is True else None


def _join_location(location: dict[str, Any]) -> str | None:
    state = _string(location.get("state")) or _string(location.get("province"))
    country = _string(location.get("country")) or _string(location.get("addressCountry"))
    parts = (_string(location.get("city")), state, country)
    joined = ", ".join(part for part in parts if part)
    return joined or None


def _string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
