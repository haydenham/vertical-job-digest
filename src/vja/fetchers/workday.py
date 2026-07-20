"""Workday `cxs` Layer-1 fetcher (`docs/05`, `docs/07`).

Endpoint (per-tenant; the seed `endpoint` column is authoritative):
``POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`` with body
``{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}``. The response carries `total`
plus one `jobPostings` page; we page by `offset`.

Two things make Workday unlike the Tier-A fetchers, and both shape this module:

- **It is the one paginated source.** We page until we've collected `total`; **any page failure
  raises `FetchError` and we return nothing** — a partial list would read as mass closures, the
  highest-stakes guard (`docs/08`, DECISIONS false-closure note). A short final tally vs. `total`
  is also a hard failure, never a silent partial. A changed per-page total permanently invalidates
  the snapshot, but the fetcher finishes a quarantined pagination walk before raising so one
  scheduled run captures the page counts/identity overlap needed to diagnose tenant behavior
  (D-091). The fetcher owns no DB connection, so diagnostic rows can never reach the diff.
- **The cxs list omits the job description**, so this is list-only (`description=None`). The full
  description is a Layer-2 concern, fetched lazily per new/changed posting later — fetching it here
  would mean hundreds of needless requests per big tenant for data Layer 1 doesn't use (D-026 era).

Mapping (confirmed against a live PJM response, D-019): ``external_id = externalPath`` (stable,
unique — the diff key D-016), ``apply_url`` = the public board URL built from the cxs host + site +
``externalPath``, ``title``, ``location = locationsText``. `postedOn` is a relative string
("Posted 2 Days Ago"), so `updated_at` stays None (a known weak spot for D-030 freshness).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from vja.fetchers.base import FetchError
from vja.fetchers.endpoints import build_endpoint
from vja.models import AtsType, Employer, RawPosting

_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"
_TIMEOUT = 30.0  # some tenants are slow (e.g. BP first page > 20s); generous, not per-company
_PAGE_SIZE = 20
_MAX_PAGES = 200  # safety cap against a bad `total` (200×20 = 4000, far above any real tenant)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PageResponse:
    payload: dict[str, Any]
    status_code: int
    latency_ms: int
    request_id: str | None
    content_type: str | None
    response_bytes: int


@dataclass
class _PaginationTrace:
    """In-memory evidence for one Workday pagination walk; never persisted with postings."""

    employer: Employer
    expected_total: int
    reported_totals: list[int]
    page_sizes: list[int]
    seen_ids: set[str]
    overlap_count: int = 0
    malformed_id_count: int = 0
    invalid_reason: str | None = None

    @classmethod
    def start(cls, employer: Employer, expected_total: int) -> _PaginationTrace:
        return cls(
            employer=employer,
            expected_total=expected_total,
            reported_totals=[],
            page_sizes=[],
            seen_ids=set(),
        )

    def observe(
        self,
        *,
        page: int,
        offset: int,
        response: _PageResponse,
        reported_total: int,
        jobs: list[Any],
        cumulative_rows: int,
    ) -> None:
        ordered_ids: list[str] = []
        page_ids: set[str] = set()
        page_overlap = 0
        malformed_ids = 0
        for job in jobs:
            external_id = job.get("externalPath") if isinstance(job, dict) else None
            if not isinstance(external_id, str) or not external_id:
                malformed_ids += 1
                ordered_ids.append("<malformed>")
                continue
            ordered_ids.append(external_id)
            if external_id in self.seen_ids or external_id in page_ids:
                page_overlap += 1
            page_ids.add(external_id)

        self.reported_totals.append(reported_total)
        self.page_sizes.append(len(jobs))
        self.seen_ids.update(page_ids)
        self.overlap_count += page_overlap
        self.malformed_id_count += malformed_ids
        page_hash = hashlib.sha256("\n".join(ordered_ids).encode()).hexdigest()[:16]
        logger.info(
            "workday pagination page employer=%r page=%d offset=%d limit=%d "
            "expected_total=%d reported_total=%d rows=%d cumulative_rows=%d unique_ids=%d "
            "page_overlap=%d malformed_ids=%d page_ids_sha256=%s http_status=%d "
            "latency_ms=%d request_id=%r content_type=%r response_bytes=%d payload_keys=%s "
            "diagnostic_only=%s",
            self.employer.name,
            page + 1,
            offset,
            _PAGE_SIZE,
            self.expected_total,
            reported_total,
            len(jobs),
            cumulative_rows,
            len(self.seen_ids),
            page_overlap,
            malformed_ids,
            page_hash,
            response.status_code,
            response.latency_ms,
            response.request_id,
            response.content_type,
            response.response_bytes,
            ",".join(sorted(response.payload)),
            self.invalid_reason is not None,
        )

    def finish(self, collected_rows: int) -> None:
        would_complete = (
            collected_rows == self.expected_total
            and len(self.seen_ids) == self.expected_total
            and self.overlap_count == 0
            and self.malformed_id_count == 0
        )
        log = logger.warning if self.invalid_reason else logger.info
        log(
            "workday pagination summary employer=%r pages=%d expected_total=%d "
            "collected_rows=%d unique_ids=%d overlap=%d malformed_ids=%d "
            "reported_totals=%s page_sizes=%s would_complete=%s diagnostic_only=%s reason=%r",
            self.employer.name,
            len(self.page_sizes),
            self.expected_total,
            collected_rows,
            len(self.seen_ids),
            self.overlap_count,
            self.malformed_id_count,
            ",".join(str(value) for value in self.reported_totals),
            ",".join(str(value) for value in self.page_sizes),
            would_complete,
            self.invalid_reason is not None,
            self.invalid_reason,
        )


class WorkdayFetcher:
    """Fetches open postings from a Workday `cxs` job board. Pure read (`docs/05`).

    A `client` may be injected (tests / connection reuse); otherwise a short-lived one is created
    per fetch with an identifiable User-Agent (politeness — `docs/05`).
    """

    ats_type: AtsType = AtsType.WORKDAY

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, employer: Employer) -> list[RawPosting]:
        url = build_endpoint(employer)
        base, site = _board_base_and_site(url, employer)
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            return _paginate(client, url, base, site, employer)
        finally:
            if self._client is None:
                client.close()

    def fetch_detail(self, employer: Employer, external_path: str) -> dict[str, Any]:
        """Fetch one posting's full cxs detail (`jobPostingInfo`) — the Layer-2 description (P5.2).

        The list endpoint (`.../jobs`) omits the description; the detail endpoint is the same path
        with `/jobs` replaced by the posting's `externalPath`. Returns the `jobPostingInfo` dict
        (has `jobDescription`, `startDate`, structured `country`). Raises `FetchError` on failure.
        """
        detail_url = build_endpoint(employer).removesuffix("/jobs") + external_path
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            response = client.get(detail_url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise FetchError(f"workday detail fetch failed for {employer.name!r}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FetchError(f"workday detail non-JSON for {employer.name!r}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        info = payload.get("jobPostingInfo") if isinstance(payload, dict) else None
        if not isinstance(info, dict):
            raise FetchError(f"workday detail for {employer.name!r} missing 'jobPostingInfo'")
        return info


def _paginate(
    client: httpx.Client, url: str, base: str, site: str, employer: Employer
) -> list[RawPosting]:
    postings: list[RawPosting] = []
    total: int | None = None
    trace: _PaginationTrace | None = None

    for page in range(_MAX_PAGES):
        offset = page * _PAGE_SIZE
        response = _post_page(client, url, offset, employer)
        payload = response.payload
        page_total = _read_total(payload, employer)
        if total is None:
            total = page_total
            trace = _PaginationTrace.start(employer, total)
        elif page_total != total:
            assert trace is not None
            if trace.invalid_reason is None:
                trace.invalid_reason = (
                    f"workday total changed during fetch for {employer.name!r}: "
                    f"{total} → {page_total}"
                )
                logger.warning(
                    "workday pagination anomaly employer=%r page=%d offset=%d "
                    "expected_total=%d reported_total=%d action=diagnostic_shadow",
                    employer.name,
                    page + 1,
                    offset,
                    total,
                    page_total,
                )
        # A total mismatch has already made this snapshot unusable. Keep walking only to learn
        # whether offset pages are empty, repeated, or complete/disjoint; the original FetchError
        # is raised below before this list can leave the fetcher (D-091).
        page_jobs = payload["jobPostings"]
        assert trace is not None
        trace.observe(
            page=page,
            offset=offset,
            response=response,
            reported_total=page_total,
            jobs=page_jobs,
            cumulative_rows=len(postings) + len(page_jobs),
        )
        for job in page_jobs:
            if not isinstance(job, dict):
                raise FetchError(f"workday job entry for {employer.name!r} is not an object")
            postings.append(_map_job(job, base, site, employer))
        if not page_jobs or len(postings) >= total:
            break

    if trace is not None and (len(trace.page_sizes) > 1 or trace.invalid_reason is not None):
        trace.finish(len(postings))
    if trace is not None and trace.invalid_reason is not None:
        raise FetchError(trace.invalid_reason)

    # Completeness guard: only an exact tally is safe. Both a short and an over-counted snapshot
    # can hide pagination drift that the diff would otherwise interpret as real board churn.
    if total is None or len(postings) != total:
        expected = total if total is not None else "unknown"
        raise FetchError(
            f"workday fetch for {employer.name!r} incomplete: got {len(postings)} of {expected}"
        )
    return postings


def _post_page(client: httpx.Client, url: str, offset: int, employer: Employer) -> _PageResponse:
    body = {"appliedFacets": {}, "limit": _PAGE_SIZE, "offset": offset, "searchText": ""}
    started = time.monotonic()
    try:
        response = client.post(url, json=body)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise FetchError(
            f"workday fetch failed for {employer.name!r} (offset {offset}): {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise FetchError(f"workday returned non-JSON for {employer.name!r}: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("jobPostings"), list):
        raise FetchError(f"workday response for {employer.name!r} missing a 'jobPostings' list")
    request_id = next(
        (
            value
            for header in ("x-request-id", "x-workday-request-id", "wd-request-id", "traceparent")
            if (value := response.headers.get(header))
        ),
        None,
    )
    return _PageResponse(
        payload=payload,
        status_code=response.status_code,
        latency_ms=round((time.monotonic() - started) * 1000),
        request_id=request_id,
        content_type=response.headers.get("content-type"),
        response_bytes=len(response.content),
    )


def _read_total(payload: dict[str, Any], employer: Employer) -> int:
    total = payload.get("total")
    if not isinstance(total, int):
        raise FetchError(f"workday response for {employer.name!r} missing an integer 'total'")
    return total


def _board_base_and_site(cxs_url: str, employer: Employer) -> tuple[str, str]:
    """Split a cxs URL into the public board base + site.

    `https://{host}/wday/cxs/{tenant}/{site}/jobs` → (`https://{host}`, `{site}`), so an apply URL
    is `{base}/{site}{externalPath}`.
    """
    base, sep, rest = cxs_url.partition("/wday/cxs/")
    segments = rest.strip("/").split("/")
    if not sep or len(segments) < 3:
        raise FetchError(f"workday endpoint for {employer.name!r} is not a cxs URL: {cxs_url!r}")
    return base, segments[1]


def _map_job(job: dict[str, Any], base: str, site: str, employer: Employer) -> RawPosting:
    """Map one Workday jobPosting to a `RawPosting`; raise `FetchError` on a missing field."""
    external_path = job.get("externalPath")
    title = job.get("title")
    if not isinstance(external_path, str) or not external_path:
        raise FetchError(f"workday job for {employer.name!r} missing 'externalPath'")
    if not isinstance(title, str) or not title:
        raise FetchError(f"workday job for {employer.name!r} missing 'title'")

    return RawPosting(
        external_id=external_path,
        title=title,
        apply_url=f"{base}/{site}{external_path}",
        location=job.get("locationsText"),
        updated_at=None,  # Workday's list gives only a relative `postedOn` string
        raw=job,
        description=None,  # list-only; the description is a lazy Layer-2 fetch
    )
