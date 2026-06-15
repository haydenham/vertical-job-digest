"""Unit tests for the daily diff arithmetic (Chunk 6).

Pure set logic, so it's pinned exhaustively including every empty/edge case — this is
the contract that decides what ships in the digest (`docs/04` lifecycle, D-009/D-016).
"""

from vja.diff import compute_diff


def test_typical_mix_of_new_kept_and_closed() -> None:
    result = compute_diff(fetched_ids=["a", "b", "c"], stored_open_ids=["b", "c", "d"])
    assert result.new == {"a"}
    assert result.still_present == {"b", "c"}
    assert result.closed == {"d"}


def test_all_new_when_nothing_stored() -> None:
    result = compute_diff(fetched_ids=["a", "b"], stored_open_ids=[])
    assert result.new == {"a", "b"}
    assert result.still_present == frozenset()
    assert result.closed == frozenset()


def test_all_closed_when_fetch_is_empty() -> None:
    # The dangerous case: an empty fetch closes everything. This is arithmetically
    # correct — the no-mass-close guard lives in the CALLER (don't diff a failed fetch).
    result = compute_diff(fetched_ids=[], stored_open_ids=["a", "b"])
    assert result.new == frozenset()
    assert result.still_present == frozenset()
    assert result.closed == {"a", "b"}


def test_both_empty_yields_all_empty() -> None:
    result = compute_diff(fetched_ids=[], stored_open_ids=[])
    assert result.new == frozenset()
    assert result.still_present == frozenset()
    assert result.closed == frozenset()


def test_no_change_keeps_everything_present() -> None:
    result = compute_diff(fetched_ids=["a", "b"], stored_open_ids=["a", "b"])
    assert result.new == frozenset()
    assert result.still_present == {"a", "b"}
    assert result.closed == frozenset()


def test_fully_disjoint_sets() -> None:
    result = compute_diff(fetched_ids=["a"], stored_open_ids=["b"])
    assert result.new == {"a"}
    assert result.still_present == frozenset()
    assert result.closed == {"b"}


def test_accepts_arbitrary_iterables_and_dedups() -> None:
    result = compute_diff(fetched_ids=iter(["a", "a", "b"]), stored_open_ids=["b", "b"])
    assert result.new == {"a"}
    assert result.still_present == {"b"}
    assert result.closed == frozenset()


def test_partitions_are_disjoint_and_cover_the_inputs() -> None:
    fetched = {"a", "b", "c"}
    stored = {"b", "c", "d", "e"}
    result = compute_diff(fetched_ids=fetched, stored_open_ids=stored)
    # pairwise disjoint
    assert result.new & result.still_present == frozenset()
    assert result.new & result.closed == frozenset()
    assert result.still_present & result.closed == frozenset()
    # coverage
    assert result.new | result.still_present == fetched
    assert result.still_present | result.closed == stored
