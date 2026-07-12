"""Generic Pinpoint Layer-1 careers fetcher."""

from __future__ import annotations

import json
from typing import Any

import httpx

from vja.fetchers.base import FetchError
from vja.fetchers.endpoints import build_endpoint
from vja.models import AtsType, Employer, RawPosting

_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"
_TIMEOUT = 30.0
_CONTENT_FIELDS = (
    "description",
    "key_responsibilities",
    "skills_knowledge_expertise",
    "benefits",
)
_COMPENSATION_FIELDS = (
    "compensation",
    "compensation_minimum",
    "compensation_maximum",
    "compensation_currency",
    "compensation_frequency",
    "compensation_visible",
)


class PinpointFetcher:
    """Fetch the authoritative single-response list for a Pinpoint board."""

    ats_type: AtsType = AtsType.PINPOINT

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
            raise FetchError(f"pinpoint fetch failed for {employer.name!r}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FetchError(f"pinpoint returned non-JSON for {employer.name!r}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise FetchError(f"pinpoint response for {employer.name!r} missing a data list")

        postings = [_map_posting(item, employer) for item in payload["data"]]
        if len({posting.external_id for posting in postings}) != len(postings):
            raise FetchError(f"pinpoint fetch for {employer.name!r} returned duplicate posting ids")
        return postings


def _map_posting(item: Any, employer: Employer) -> RawPosting:
    if not isinstance(item, dict):
        raise FetchError(f"pinpoint posting for {employer.name!r} is not an object")
    try:
        raw_id = item["id"]
        raw_title = item["title"]
        raw_url = item["url"]
    except KeyError as exc:
        raise FetchError(
            f"pinpoint posting for {employer.name!r} missing required field {exc}"
        ) from exc

    if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
        raise FetchError(f"pinpoint posting for {employer.name!r} has an empty required field")
    external_id = str(raw_id).strip()
    title = raw_title.strip() if isinstance(raw_title, str) else ""
    apply_url = raw_url.strip() if isinstance(raw_url, str) else ""
    if not external_id or not title or not apply_url:
        raise FetchError(f"pinpoint posting for {employer.name!r} has an empty required field")

    return RawPosting(
        external_id=external_id,
        title=title,
        apply_url=apply_url,
        location=_location(item),
        updated_at=None,
        raw=item,
        description=_content_for_hash(item),
    )


def _location(item: dict[str, Any]) -> str | None:
    location = item.get("location")
    if not isinstance(location, dict):
        return None
    name = location.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _content_for_hash(item: dict[str, Any]) -> str | None:
    """Join Pinpoint's split rich-content fields into one stable hash input."""
    parts = [
        value.strip()
        for field in _CONTENT_FIELDS
        if isinstance((value := item.get(field)), str) and value.strip()
    ]
    compensation = {
        field: item[field] for field in _COMPENSATION_FIELDS if item.get(field) is not None
    }
    if compensation:
        parts.append(json.dumps(compensation, ensure_ascii=False, sort_keys=True))
    return "\n".join(parts) or None
