"""The common Layer-1 fetcher contract (`docs/05`).

Every ATS is a module behind this one Protocol, so an employer record is just
"a pointer to a fetcher + an identifier." Adding an ATS = adding a module that
satisfies `Fetcher`; adding an employer = adding a seed row.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

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
