"""Generic Rippling ATS Layer-1 list fetcher and lazy detail resolver."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx

from vja.fetchers.base import FetchError, joined_body
from vja.fetchers.endpoints import build_endpoint
from vja.models import AtsType, Employer, RawPosting

_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"
_TIMEOUT = 30.0


class RipplingFetcher:
    """Fetch the authoritative single-response job list for one Rippling board.

    The board API answers with a bare JSON array holding the complete open set: it ignores
    `limit`/`offset`/`page` entirely (verified live — a `?limit=5` still returned all 38 jobs),
    and an unknown slug is a clean 404. So this is the single-response false-closure guard
    (Workable/Pinpoint/BambooHR, D-049/D-079), not paginate-or-fail: a clean 200 *is* the
    complete set, an empty array is a legitimate zero, and any error raises `FetchError`
    rather than reading as "this employer closed everything".

    The list omits the body, so Rippling is a list-only ATS (D-050): extraction resolves the
    description lazily per in-scope survivor via `fetch_detail`, and keeps it via
    `detail_description` (D-095).
    """

    ats_type: AtsType = AtsType.RIPPLING

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, employer: Employer) -> list[RawPosting]:
        list_url = build_endpoint(employer)
        payload = self._get_json(list_url, employer, "list")
        if not isinstance(payload, list):
            raise FetchError(f"rippling response for {employer.name!r} is not a job list")
        return _map_jobs(payload, employer)

    def fetch_detail(self, employer: Employer, external_id: str) -> dict[str, Any]:
        """Return one job's full detail payload (the list carries no body)."""
        detail_url = f"{build_endpoint(employer)}/{quote(external_id, safe='')}"
        payload = self._get_json(detail_url, employer, "detail")
        if not isinstance(payload, dict):
            raise FetchError(f"rippling detail for {employer.name!r} is not an object")
        if _description_fragments(payload.get("description")) == ():
            raise FetchError(f"rippling detail for {employer.name!r} missing job description")
        return payload

    def detail_description(self, payload: dict[str, Any]) -> str | None:
        """The posting body out of a `fetch_detail` payload (D-095).

        Rippling splits the body into `description.role` (this posting) and
        `description.company` (identical boilerplate on every job at that employer), so this is
        the Pinpoint split-content case `joined_body` exists for. `role` leads: it is the
        substantive text, and it is what a reader opening the detail panel came for.
        """
        return joined_body(*_description_fragments(payload.get("description")))

    def _get_json(self, url: str, employer: Employer, operation: str) -> Any:
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            response = client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise FetchError(
                f"rippling {operation} fetch failed for {employer.name!r}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise FetchError(
                f"rippling {operation} returned non-JSON for {employer.name!r}: {exc}"
            ) from exc
        finally:
            if self._client is None:
                client.close()


def _map_jobs(entries: list[Any], employer: Employer) -> list[RawPosting]:
    """Group the list's (job × location) rows back into one posting per job.

    Rippling denormalizes: a role open in four cities is four list entries sharing one `uuid`,
    identical in every field but `workLocation`. That is a provider shape, not the snapshot
    defect D-088's duplicate-id guard was written for, so the locations merge (the Workday
    `locationsText` / Oracle `secondaryLocations` treatment of a multi-location req). The guard
    itself survives, narrowed: entries sharing a `uuid` that disagree on *anything else* are a
    genuine integrity violation and still fail the whole snapshot with zero mutation.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        groups.setdefault(_external_id(entry, employer), []).append(entry)
    return [_map_group(external_id, group, employer) for external_id, group in groups.items()]


def _external_id(job: Any, employer: Employer) -> str:
    """Validate one list entry and return its `uuid` (the D-016 diff key)."""
    if not isinstance(job, dict):
        raise FetchError(f"rippling job entry for {employer.name!r} is not an object")
    try:
        raw_id = job["uuid"]
        raw_title = job["name"]
        raw_url = job["url"]
    except KeyError as exc:
        raise FetchError(
            f"rippling job for {employer.name!r} missing required field {exc}"
        ) from exc

    external_id = raw_id.strip() if isinstance(raw_id, str) else ""
    title = raw_title.strip() if isinstance(raw_title, str) else ""
    apply_url = raw_url.strip() if isinstance(raw_url, str) else ""
    if not external_id or not title or not apply_url:
        raise FetchError(f"rippling job for {employer.name!r} has an empty required field")
    return external_id


def _map_group(external_id: str, group: list[dict[str, Any]], employer: Employer) -> RawPosting:
    first = group[0]
    baseline = _without_location(first)
    for other in group[1:]:
        if _without_location(other) != baseline:
            raise FetchError(
                f"rippling job {external_id!r} for {employer.name!r} repeats with conflicting "
                "fields beyond its work location"
            )

    return RawPosting(
        external_id=external_id,
        title=str(first["name"]).strip(),
        # Rippling supplies the canonical board URL per job, so it is never constructed.
        apply_url=str(first["url"]).strip(),
        location=_locations(group),
        # The list carries no date; `createdOn` exists only on the detail payload, and the
        # diff runs off the list (Pinpoint precedent, D-079).
        updated_at=None,
        raw=first,
        description=None,
    )


def _without_location(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key != "workLocation"}


def _locations(group: list[dict[str, Any]]) -> str | None:
    """The group's distinct work locations, **sorted**, as one "; "-joined string.

    Sorted rather than API order on purpose: `content_hash` keys on `location`
    (`vja.hashing`), so a board that reorders its rows between nights would otherwise flip
    every multi-location posting's hash and trigger a corpus-wide false "content changed" —
    the exact churn D-088 exists to prevent.
    """
    labels = {label for job in group if (label := _location(job)) is not None}
    return "; ".join(sorted(labels)) or None


#: `description.role` first — see `RipplingFetcher.detail_description`.
_DESCRIPTION_FIELDS = ("role", "company")


def _description_fragments(description: Any) -> tuple[str, ...]:
    """The non-empty body fragments in a detail payload's `description`, in render order.

    Every tenant probed returns the two-key object; a bare string is accepted defensively so a
    shape change degrades to "one fragment" instead of a fetch failure for every posting.
    """
    if isinstance(description, str):
        return (description,) if description.strip() else ()
    if not isinstance(description, dict):
        return ()
    return tuple(
        value
        for field in _DESCRIPTION_FIELDS
        if isinstance((value := description.get(field)), str) and value.strip()
    )


def _location(job: dict[str, Any]) -> str | None:
    location = job.get("workLocation")
    if not isinstance(location, dict):
        return None
    label = location.get("label")
    return label.strip() if isinstance(label, str) and label.strip() else None
