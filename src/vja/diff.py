"""Daily diff set arithmetic — the core of "the diff is the product" (`docs/04` lifecycle).

Pure set logic over `external_id`s (the diff key, D-016); no DB, no I/O. For one
employer per nightly fetch:

    new           = fetched − stored_open   → insert as open, flag for Layer-2 extraction
    still_present = fetched ∩ stored_open   → bump last_seen (re-extract if content_hash changed)
    closed        = stored_open − fetched   → mark closed, NEVER delete (D-009)

CRITICAL — the no-mass-close guard (`docs/05`): this function cannot distinguish
"the board is genuinely empty today" from "the fetch failed." It faithfully computes
`closed = stored − fetched` even when `fetched` is empty. The CALLER must only invoke
`compute_diff` on a **successful** fetch — a fetch that raised `FetchError` must skip
the diff entirely, otherwise a transient 500 would close every posting and ship a
digest claiming the whole company's jobs died.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class DiffResult:
    """The three disjoint partitions of a fetch vs. what was stored open.

    Invariants: the three sets are pairwise disjoint; `new | still_present == fetched`
    and `still_present | closed == stored_open`.
    """

    new: frozenset[str]
    still_present: frozenset[str]
    closed: frozenset[str]


def compute_diff(fetched_ids: Iterable[str], stored_open_ids: Iterable[str]) -> DiffResult:
    """Partition this fetch against the currently-open postings for one employer.

    Accepts any iterables of `external_id` (lists, sets, generators); duplicates are
    collapsed by set semantics.
    """
    fetched = frozenset(fetched_ids)
    stored = frozenset(stored_open_ids)
    return DiffResult(
        new=fetched - stored,
        still_present=fetched & stored,
        closed=stored - fetched,
    )
