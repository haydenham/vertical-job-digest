"""The common Layer-1 fetcher contract (`docs/05`).

Every ATS is a module behind this one Protocol, so an employer record is just
"a pointer to a fetcher + an identifier." Adding an ATS = adding a module that
satisfies `Fetcher`; adding an employer = adding a seed row.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from vja.models import AtsType, Employer, RawPosting


class FetchError(Exception):
    """Raised on any transport/parse failure inside a fetcher.

    The pipeline catches this, records a `fetch_failure`, and alerts — it is never
    swallowed (`docs/05`, `docs/09`: no bare `except: pass`). Silent decay is the
    enemy. Critically, a raised `FetchError` must NOT be read as "this employer has
    zero open jobs": that would mass-close yesterday's postings on a transient error
    (the highest-stakes guard — `docs/08`). The diff only runs on a successful fetch.
    """


@runtime_checkable
class Fetcher(Protocol):
    """Returns the currently-open postings for an employer. Pure read.

    Implementations are deterministic, read-only, and idempotent — no DB writes
    happen inside a fetcher (`docs/05`); it returns data and the diff job persists.
    A fetcher only produces `RawPosting`; it does NOT extract structured fields
    (level, stack, comp) — that is Layer 2.
    """

    ats_type: AtsType

    def fetch(self, employer: Employer) -> list[RawPosting]:
        """Return all currently-open postings for `employer`.

        Raises `FetchError` on any non-200 / unparseable response.
        """
        ...


@runtime_checkable
class ListOnlyFetcher(Protocol):
    """A `Fetcher` whose list endpoint omits the job body, so the body is a second, lazy call.

    Extraction fetches that detail per in-scope survivor (cost discipline, D-035) and then asks
    the same fetcher where the body lives inside it — the provider shape is the fetcher's business,
    not extraction's. Both methods take their id positionally: Workday's is an `externalPath`, the
    others a bare id.
    """

    def fetch_detail(self, employer: Employer, external_id: str, /) -> dict[str, Any]:
        """Return one posting's full detail payload. Raises `FetchError` on failure."""
        ...

    def detail_description(self, payload: dict[str, Any], /) -> str | None:
        """Return the posting body held in a `fetch_detail` payload, or `None` (D-095)."""
        ...


def joined_body(*fragments: object) -> str | None:
    """Join a detail payload's body fragments into one description string, or `None`.

    The list-only ATSs each expose `detail_description(payload)` beside their `fetch_detail`, so
    extraction can keep the body it already fetched (D-095) instead of discarding it. Their
    payloads differ only in *where* the text lives — one field (Workday), a handful of parallel
    fields (Oracle), or titled sections (SmartRecruiters) — so this holds the one shared rule:
    non-string and blank fragments are dropped, survivors are separated by a blank line, and an
    empty result is `None` rather than `""` (the column means "no body", not "an empty body").
    Fragments are returned in the provider's own shape — HTML included; normalization to plain
    text happens once, at the `vja.text` boundary.
    """
    parts = [fragment.strip() for fragment in fragments if isinstance(fragment, str)]
    return "\n\n".join(part for part in parts if part) or None
