"""Unit tests for `content_hash` (Chunk 3).

This is the extraction cache's correctness, so the contract is pinned hard
(`docs/04` §3, `docs/08`): deterministic, order-independent, whitespace-invariant,
volatile-junk-excluded, and sensitive to every real content field.
"""

from vja.hashing import content_hash


def test_is_deterministic_64_char_hex() -> None:
    h1 = content_hash(title="Engineer", location="Austin", description="Do the thing.")
    h2 = content_hash(title="Engineer", location="Austin", description="Do the thing.")
    assert h1 == h2
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


def test_golden_value_locks_the_canonical_form() -> None:
    # Regression lock: any change to normalization/serialization changes this and
    # must be a deliberate, reviewed decision (the cache would otherwise silently
    # invalidate every stored extraction).
    assert (
        content_hash(
            title="Software Engineer",
            location="Austin, TX",
            description="Build the grid.",
        )
        == "4ec62775e4f48f49bdd4468df875b66441e1edc8cf3bd18eac5275150fa40e1d"
    )


def test_whitespace_is_normalized_away() -> None:
    tight = content_hash(title="Senior Engineer", location="New York", description="A B C")
    loose = content_hash(
        title="  Senior   Engineer ",
        location="New York",
        description="A\n\tB   C\n",
    )
    assert tight == loose


def test_none_and_empty_hash_identically() -> None:
    assert content_hash(title="X", location=None, description=None) == content_hash(
        title="X", location="", description=""
    )


def test_changing_description_changes_the_hash() -> None:
    base = content_hash(title="X", location="Y", description="original")
    changed = content_hash(title="X", location="Y", description="edited")
    assert base != changed


def test_changing_title_changes_the_hash() -> None:
    base = content_hash(title="X", location="Y", description="d")
    changed = content_hash(title="X2", location="Y", description="d")
    assert base != changed


def test_changing_location_changes_the_hash() -> None:
    base = content_hash(title="X", location="Y", description="d")
    changed = content_hash(title="X", location="Z", description="d")
    assert base != changed


def test_case_is_significant() -> None:
    # Case carries meaning ("Senior" vs "senior") — a case change is a content change.
    assert content_hash(title="Senior", location="NY", description="d") != content_hash(
        title="senior", location="NY", description="d"
    )


def test_volatile_payload_fields_are_excluded_by_construction() -> None:
    # The cache must not invalidate just because the ATS bumped a view count or a
    # "scraped at" timestamp. Callers hash only the stable fields, so two fetches of
    # the same role with different volatile metadata collapse to the same hash.
    def stable_hash_from_payload(payload: dict[str, object]) -> str:
        return content_hash(
            title=str(payload["title"]),
            location=str(payload["location"]),
            description=str(payload["description"]),
        )

    monday = {
        "title": "Engineer",
        "location": "Austin",
        "description": "Build it.",
        "view_count": 12,
        "scraped_at": "2026-06-15T00:00:00Z",
        "apply_url": "https://x.com/1?utm_source=monday",
    }
    tuesday = {
        "title": "Engineer",
        "location": "Austin",
        "description": "Build it.",
        "view_count": 87,
        "scraped_at": "2026-06-16T00:00:00Z",
        "apply_url": "https://x.com/1?utm_source=tuesday",
    }
    assert stable_hash_from_payload(monday) == stable_hash_from_payload(tuesday)
