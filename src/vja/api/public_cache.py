"""In-process TTL cache for the public demo board's responses (D-105).

**Caching is the abuse guard.** There is no rate limiting anywhere in this application, and
`/api/public/*` is the first surface an unauthenticated stranger can call at will. The data behind
it changes at most every four hours (D-103), so a short TTL keeps a burst of repeat traffic off
Neon entirely while costing correctness nothing that the pipeline cadence doesn't already cost.
The HTTP `Cache-Control` the endpoints set is the other half: this cache absorbs what reaches the
process, Cloudflare's edge absorbs what never should.

Deliberately in-process and unshared: Cloud Run may run several instances, so this is N independent
caches, each of which is simply a warm instance serving a slightly older list. That is the correct
trade for a board whose rows move every four hours, and it avoids introducing Redis for it.

Not used for the per-posting body: that key space is unbounded (one entry per posting id) and each
open is a single indexed lookup, so caching it would trade memory for nothing.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field

# One pipeline pass lands new rows at most every four hours (D-103), so a five-minute window is
# invisible to a reader and still collapses a burst of traffic from one link into a single query.
DEFAULT_TTL_SECONDS = 300.0

# A hard bound so a hostile caller cannot grow the cache without limit by varying the key. The real
# key space is (vertical × window) = low double digits; anything beyond that is abuse or a bug, and
# the oldest entry is evicted rather than the newest refused.
DEFAULT_MAX_ENTRIES = 64


@dataclass
class TTLCache[V]:
    """A tiny time-bounded memo. `monotonic` is injected so tests can move time without sleeping.

    Not thread-safe by design: the worst a race can do here is compute the same list twice and
    store the same value twice, and buying a lock for that would slow every hit to protect nothing.
    """

    ttl_seconds: float = DEFAULT_TTL_SECONDS
    max_entries: int = DEFAULT_MAX_ENTRIES
    monotonic: Callable[[], float] = time.monotonic
    _entries: dict[Hashable, tuple[float, V]] = field(default_factory=dict)

    def get_or_compute(self, key: Hashable, compute: Callable[[], V]) -> V:
        """The cached value for `key`, computing (and storing) it when absent or stale."""
        now = self.monotonic()
        hit = self._entries.get(key)
        if hit is not None and now - hit[0] < self.ttl_seconds:
            return hit[1]

        value = compute()
        # Insertion order is age order (dicts preserve it and a refresh re-inserts below), so the
        # first key is the oldest.
        self._entries.pop(key, None)
        while len(self._entries) >= self.max_entries:
            self._entries.pop(next(iter(self._entries)))
        self._entries[key] = (now, value)
        return value

    def clear(self) -> None:
        """Drop everything — used by tests, and available if an operator ever needs it."""
        self._entries.clear()
