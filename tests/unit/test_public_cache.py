"""Unit tests for the public board's TTL cache (D-105).

Time is injected rather than slept on: a cache test that sleeps is a slow test that later gets
skipped, and `docs/08` pushes coverage down the pyramid precisely so it stays run.
"""

from vja.api.public_cache import TTLCache


class _Clock:
    """A hand-cranked monotonic clock."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def test_a_hit_inside_the_ttl_does_not_recompute() -> None:
    clock = _Clock()
    cache: TTLCache[int] = TTLCache(ttl_seconds=300, monotonic=clock)
    calls = 0

    def compute() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert cache.get_or_compute("k", compute) == 1
    clock.now += 299
    assert cache.get_or_compute("k", compute) == 1
    assert calls == 1


def test_the_entry_expires_at_the_ttl() -> None:
    clock = _Clock()
    cache: TTLCache[str] = TTLCache(ttl_seconds=300, monotonic=clock)

    assert cache.get_or_compute("k", lambda: "first") == "first"
    clock.now += 300
    assert cache.get_or_compute("k", lambda: "second") == "second"


def test_distinct_keys_are_cached_independently() -> None:
    cache: TTLCache[str] = TTLCache(monotonic=_Clock())

    assert cache.get_or_compute(("grid", "all"), lambda: "grid rows") == "grid rows"
    assert cache.get_or_compute(("aviation", "all"), lambda: "aviation rows") == "aviation rows"
    assert cache.get_or_compute(("grid", "all"), lambda: "recomputed") == "grid rows"


def test_the_size_bound_evicts_the_oldest_entry() -> None:
    """The bound is what stops a hostile caller growing the cache by varying the key. Eviction is
    oldest-first, so the entry a real visitor just warmed is not the one thrown away."""
    cache: TTLCache[int] = TTLCache(max_entries=2, monotonic=_Clock())

    cache.get_or_compute("a", lambda: 1)
    cache.get_or_compute("b", lambda: 2)
    cache.get_or_compute("c", lambda: 3)

    assert cache.get_or_compute("a", lambda: 99) == 99  # evicted → recomputed
    assert cache.get_or_compute("c", lambda: 99) == 3  # still warm


def test_a_refresh_does_not_grow_the_cache() -> None:
    """Re-caching an existing key must replace it, not accumulate a second entry that pushes a
    live key out of a full cache."""
    clock = _Clock()
    cache: TTLCache[int] = TTLCache(ttl_seconds=10, max_entries=2, monotonic=clock)

    cache.get_or_compute("a", lambda: 1)
    cache.get_or_compute("b", lambda: 2)
    clock.now += 10
    cache.get_or_compute("a", lambda: 11)

    assert cache.get_or_compute("b", lambda: 22) == 22  # b expired, not evicted early
    assert cache.get_or_compute("a", lambda: 99) == 11  # a is still the warm entry


def test_clear_drops_everything() -> None:
    cache: TTLCache[int] = TTLCache(monotonic=_Clock())
    cache.get_or_compute("k", lambda: 1)
    cache.clear()
    assert cache.get_or_compute("k", lambda: 2) == 2
