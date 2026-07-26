"""Radancy / TalentBrew Layer-1 fetcher (`docs/05`, `docs/07`).

Radancy (formerly TalentBrew) powers a family of enterprise career portals whose landing page is
a JS shell, but whose **server-rendered search-results endpoint** returns the jobs as HTML — the
same markup for every tenant, so this is one generic per-platform fetcher, never a per-company
scraper (D-017/D-004). The visible-portal-is-empty-but-the-product-has-an-endpoint shape mirrors
the iCIMS lesson (D-048).

``GET {endpoint}/search-jobs/results`` with ``startrow={offset}`` and reference-date sorting →
an HTML page with a ``<table id="searchresults">`` of ``<tr class="data-row">`` job rows. The
table's ``aria-label`` carries the grand total ("Results 1 to 25 **of 288**") — the completeness
anchor. The per-tenant host differs, so the seed ``endpoint`` is **explicit per-tenant** (not
slug-derived), like iCIMS/Oracle.

The contract mirrors **Workday/SmartRecruiters/Oracle** (`docs/07`): list-only + paginate-or-fail
+ a lazy detail fetch.

- **List-only.** The results rows carry title, location, and date but **no description**. The
  description lives only on the per-job page and is fetched lazily, per in-scope survivor, by
  Layer-2 extraction (`extract.py`) via ``fetch_detail`` (cost discipline, D-035) — exactly like
  Workday.
- **Paginate fully or fail.** The ``of N`` total drives pagination; a short final tally (or an
  unparseable total) is a hard `FetchError` (a truncated/mis-parsed HTML scrape must never read as
  mass closures — the false-closure guard, `docs/08`). HTML parsing is markup-fragile, so this
  guard plus the pipeline's N>0→0 health check (`docs/05`) are the safety net: any structural
  surprise raises, never a silent partial.

Mapping (`docs/05`): ``external_id`` = the ``/job/{slug}/{id}`` path — the stable diff key carried
on the apply URL (D-016). Like **Workday's ``externalPath``** (D-032) it embeds the numeric req id
plus a slug; the slug is what the detail URL needs (the id alone 404s), and ``fetch_detail`` takes
only ``(employer, external_id)``, so the path *is* the id. (Same theoretical retitle-churn risk
Workday already accepts.) ``apply_url`` is that path made absolute; ``title`` from the link text;
``location`` from the row's ``jobLocation`` cell; ``updated_at`` from the ``jobDate`` cell parsed
to an ISO date (a D-030 freshness win). ``description = None`` (lazy — see ``fetch_detail``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from vja.fetchers.base import FetchError, joined_body
from vja.fetchers.endpoints import build_endpoint
from vja.models import AtsType, Employer, RawPosting

_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"
_TIMEOUT = 30.0
_MAX_PAGES = 200  # safety cap against a bad total (the live board serves 25 rows per page)
_SEARCH_PATH = "/search-jobs/results"
_JOB_PREFIX = "/job/"
_DATE_FORMAT = "%b %d, %Y"  # the TalentBrew jobDate cell, e.g. "Jun 24, 2026"


class RadancyFetcher:
    """Fetches open postings from a Radancy/TalentBrew career portal. Pure read (`docs/05`).

    A `client` may be injected (tests / connection reuse); otherwise a short-lived one is created
    per fetch with an identifiable User-Agent (politeness — `docs/05`).
    """

    ats_type: AtsType = AtsType.RADANCY

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, employer: Employer) -> list[RawPosting]:
        base = build_endpoint(employer).rstrip("/")
        list_url = f"{base}{_SEARCH_PATH}"
        origin = _origin(base)
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            return _paginate(client, list_url, origin, employer)
        finally:
            if self._client is None:
                client.close()

    def fetch_detail(self, employer: Employer, external_id: str) -> dict[str, str | None]:
        """Fetch one posting's job page and return its description (`div.jobdescription`).

        ``external_id`` is the ``/job`` path, so the detail page is ``{origin}/job/{external_id}/``.
        Returns a dict (handed to the extraction model like the other resolvers); raises
        `FetchError` on transport failure or a redirect to the portal's error page.
        """
        origin = _origin(build_endpoint(employer).rstrip("/"))
        url = f"{origin}{_JOB_PREFIX}{external_id.strip('/')}/"
        client = self._client or httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        try:
            response = client.get(url, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise FetchError(f"radancy detail fetch failed for {employer.name!r}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        if "errorpage" in str(response.url):  # id-only / stale path → portal error redirect
            raise FetchError(f"radancy detail for {employer.name!r} hit an error page: {url}")

        soup = BeautifulSoup(response.text, "html.parser")
        desc = soup.select_one("div.jobdescription") or soup.select_one("[itemprop=description]")
        return {"description": desc.get_text(" ", strip=True) if desc else None, "url": url}

    def detail_description(self, payload: dict[str, Any]) -> str | None:
        """The posting body out of a `fetch_detail` payload.

        Already plain text — this fetcher flattens the job page itself, and that flattened string
        is what `content_hash` keys on, so its shape must not change here (D-095).
        """
        return joined_body(payload.get("description"))


def _origin(url: str) -> str:
    """The scheme://host of `url` — job hrefs are root-relative, so apply/detail URLs join here."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _paginate(
    client: httpx.Client, list_url: str, origin: str, employer: Employer
) -> list[RawPosting]:
    postings: list[RawPosting] = []
    total: int | None = None
    offset = 0

    for _page in range(_MAX_PAGES):
        soup = _get_page(client, list_url, offset, employer)
        table = soup.select_one("table#searchresults")
        if table is None:
            if offset == 0 and _is_empty_board(soup):
                return []  # a legitimately empty board, not a breakage
            raise FetchError(f"radancy response for {employer.name!r} has no results table")
        page_total = _read_total(table, employer)
        if total is None:
            total = page_total
        elif page_total != total:
            raise FetchError(
                f"radancy total changed during fetch for {employer.name!r}: {total} → {page_total}"
            )
        rows = table.select("tbody tr.data-row")
        if not rows:
            break
        for row in rows:
            postings.append(_map_row(row, origin, employer))
        if len(postings) >= total:
            break
        offset += len(rows)

    # Completeness guard: only an exact tally is safe. Both a short and an over-counted scrape can
    # hide pagination drift that the diff would otherwise interpret as real board churn.
    if total is None or len(postings) != total:
        expected = total if total is not None else "unknown"
        raise FetchError(
            f"radancy fetch for {employer.name!r} incomplete: {len(postings)} of {expected}"
        )
    return postings


def _get_page(
    client: httpx.Client, list_url: str, offset: int, employer: Employer
) -> BeautifulSoup:
    try:
        response = client.get(
            list_url,
            params={
                "q": "",
                "sortColumn": "referencedate",
                "sortDirection": "desc",
                "startrow": offset,
            },
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FetchError(
            f"radancy fetch failed for {employer.name!r} (offset {offset}): {exc}"
        ) from exc
    return BeautifulSoup(response.text, "html.parser")


def _is_empty_board(soup: BeautifulSoup) -> bool:
    """A TalentBrew board with zero open roles renders a no-results notice instead of the table."""
    return soup.select_one(".search-no-results, .no-results, #no-results") is not None


def _read_total(table: Tag, employer: Employer) -> int:
    """The grand total from the results table's aria-label ("Results 1 to 25 of 288")."""
    label = table.get("aria-label")
    if isinstance(label, str):
        marker = "of "
        idx = label.rfind(marker)
        if idx != -1:
            digits = label[idx + len(marker) :].strip().split()[0].replace(",", "")
            if digits.isdigit():
                return int(digits)
    raise FetchError(f"radancy results table for {employer.name!r} has no parseable total")


def _map_row(row: Tag, origin: str, employer: Employer) -> RawPosting:
    """Map one results-table row to a `RawPosting`; raise `FetchError` on a missing field."""
    link = row.select_one("a.jobTitle-link")
    href = link.get("href") if link is not None else None
    title = link.get_text(strip=True) if link is not None else None
    if not isinstance(href, str) or not href.startswith(_JOB_PREFIX):
        raise FetchError(f"radancy row for {employer.name!r} has no job link")
    if not title:
        raise FetchError(f"radancy row for {employer.name!r} missing a title")

    external_id = href[len(_JOB_PREFIX) :].strip("/")  # "{slug}/{id}" — the stable diff key (D-016)
    if not external_id:
        raise FetchError(f"radancy row for {employer.name!r} has an empty job path")

    location = _cell_text(row, "td.colLocation .jobLocation") or _cell_text(row, ".jobLocation")
    return RawPosting(
        external_id=external_id,
        title=title,
        apply_url=urljoin(origin, href),
        location=location,
        updated_at=_row_date(row),
        raw={
            "external_id": external_id,
            "title": title,
            "apply_url": urljoin(origin, href),
            "location": location,
            "date": _cell_text(row, "td.colDate .jobDate") or _cell_text(row, ".jobDate"),
        },
        description=None,  # list-only; the description is a lazy Layer-2 fetch (`fetch_detail`)
    )


def _cell_text(row: Tag, selector: str) -> str | None:
    el = row.select_one(selector)
    if el is None:
        return None
    text = el.get_text(" ", strip=True)
    return text or None


def _row_date(row: Tag) -> str | None:
    """The ``jobDate`` cell ("Jun 24, 2026") normalized to an ISO date; None if absent/bad."""
    raw = _cell_text(row, "td.colDate .jobDate") or _cell_text(row, ".jobDate")
    if not raw:
        return None
    try:
        return datetime.strptime(raw, _DATE_FORMAT).date().isoformat()
    except ValueError:
        return None
