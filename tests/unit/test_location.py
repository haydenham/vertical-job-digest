"""Unit tests for `us_location_display` — the location-display normalizer (D-106).

Nearly every string below is a **real production location** lifted from `postings.location` in the
dev DB, because the whole point of the module is that boards write the same place four ways. The
suite pins both directions: what must be rewritten, and what must be left alone (the more important
half — a wrong normalization misstates a real posting's location).
"""

from __future__ import annotations

import pytest

from vja import prefilter
from vja.location import _FOREIGN_CITIES, _ISO_COLLIDING, _US_STATES, us_location_display

# (raw, expected) — real rows that should normalize. Grouped by the noise they carry.
REAL_NORMALIZATIONS = [
    # Bare state codes (the common case).
    ("Kinston, NC", "Kinston, North Carolina"),
    ("Wichita, KS", "Wichita, Kansas"),
    ("Mountain View, CA", "Mountain View, California"),
    ("Boston, MA", "Boston, Massachusetts"),
    ("Herndon Area, VA", "Herndon Area, Virginia"),
    ("New York, NY", "New York, New York"),
    # Workday's leading country affix.
    ("USA - Seal Beach, CA", "Seal Beach, California"),
    ("USA - Hazelwood, MO", "Hazelwood, Missouri"),
    ("USA - Tinker AFB, OK", "Tinker AFB, Oklahoma"),
    # Oracle's leading "US,".
    ("US, Dayton, OH", "Dayton, Ohio"),
    ("US, Indianapolis, IN", "Indianapolis, Indiana"),
    # Trailing country.
    ("Atlanta, GA, United States", "Atlanta, Georgia"),
    ("Birmingham, AL, United States", "Birmingham, Alabama"),
    ("Houston, TX, United States", "Houston, Texas"),
    # Trailing country with the state already spelled out — only the affix comes off.
    ("New York, New York, United States", "New York, New York"),
    # ZIPs, alone and stacked with a country affix.
    ("Welch, MN, 55089", "Welch, Minnesota"),
    ("West Palm Beach, FL, US, 33407", "West Palm Beach, Florida"),
    # A bare trailing "USA" with no comma — the rewrite inserts the comma the board omitted.
    ("Wilmington NC USA", "Wilmington, North Carolina"),
    ("Charleroi USA", "Charleroi"),
    # Multi-site postings: every segment normalizes, the "; " join survives.
    (
        "Jacksonville, Florida; Atlanta, Georgia; Kinston, NC",
        "Jacksonville, Florida; Atlanta, Georgia; Kinston, North Carolina",
    ),
]

# Real rows that must survive untouched — `None` means "render the stored string verbatim".
REAL_PASS_THROUGH = [
    # Already in the target form.
    "Olathe, Kansas",
    "Dallas, Texas",
    "Washington, DC",  # never expanded to "District of Columbia"
    "Washington, Washington, DC",
    # Not a place at all (Workday's multi-site count) — no state token, no affix.
    "2 Locations",
    "5 Locations",
    "Remote",
    # A multi-site row already in the target form — shouty casing is left alone (no title-casing:
    # it mangles "McLean", "NASA Ames", "IBM").
    "Braceville, Illinois; WARRENVILLE, Illinois",
    # Foreign, by explicit country name.
    "Bengaluru, Karnataka, India",
    "London, England, United Kingdom",
    "Hyderabad, India",
    "Krakow, Małopolskie, Poland",
    # Foreign, by a code that is not a US state at all.
    "London, UK",
    "Tokyo, JP",
    "Mexico City, MX",
    "Montreal, QC",
    "GBR - Bristol, UK",
    # Foreign, where the code *is* a US state code — the measured collisions.
    "Buenos Aires, AR",
    "Bogota, CO",
    "Gurugram, IN",
    # No country/state signal of any kind.
    "Getafe Area",
    "Immenstaad am Bodensee",
    "Hyderabad TS IN 26",
]


@pytest.mark.parametrize(("raw", "expected"), REAL_NORMALIZATIONS)
def test_real_locations_normalize(raw: str, expected: str) -> None:
    assert us_location_display(raw) == expected


@pytest.mark.parametrize("raw", REAL_PASS_THROUGH)
def test_real_locations_pass_through_unchanged(raw: str) -> None:
    assert us_location_display(raw) is None


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_blank_input_has_no_display(raw: str | None) -> None:
    assert us_location_display(raw) is None


def test_normalization_is_idempotent() -> None:
    """Re-normalizing an already-normalized string must be a no-op, or the field is unstable."""
    for raw, expected in REAL_NORMALIZATIONS:
        assert us_location_display(expected) is None, raw


def test_duplicate_segments_collapse_in_order() -> None:
    """Two spellings of one office must not normalize into a visible stutter."""
    assert (
        us_location_display("Washington, Washington, DC; Washington, Washington, DC")
        == "Washington, Washington, DC"
    )
    assert us_location_display("USA - Chicago, IL; Chicago, Illinois") == "Chicago, Illinois"
    assert (
        us_location_display("Oswego, New York; Ontario, New York; Oswego, New York")
        == "Oswego, New York; Ontario, New York"
    )


def test_dash_delimited_rows_lose_the_country_and_keep_their_order() -> None:
    """A documented residual, pinned so a future change is deliberate.

    Some boards write `Country - State - City`. The country comes off, but the dash order is left
    alone: reordering to "Houston, Texas" is a rule with more risk than reach — 80 postings
    corpus-wide, 1 of them in-scope and open.
    """
    assert us_location_display("United States of America - Texas - Houston") == "Texas - Houston"
    assert us_location_display("USA-TX-Houston") == "TX-Houston"


def test_a_lone_ambiguous_code_stays_a_code() -> None:
    """ "IN" with no city before it could be India; only an explicit US mention settles it."""
    assert us_location_display("IN") is None
    assert us_location_display("USA - IN") == "Indiana"


def test_lowercase_trailing_token_is_not_read_as_a_state() -> None:
    """ "Portland, or" is a sentence fragment, not Oregon."""
    assert us_location_display("Portland, or") is None


def test_explicit_us_signal_beats_a_colliding_country_code() -> None:
    """A foreign-city guard must not block a genuinely US row that names the country."""
    assert us_location_display("USA - Ontario, CA") == "Ontario, California"


def test_foreign_city_guard_only_covers_colliding_codes() -> None:
    """Every `_FOREIGN_CITIES` key must be a state code that is also an ISO country code —
    otherwise the entry is dead weight the expansion path never consults."""
    assert set(_FOREIGN_CITIES) <= _ISO_COLLIDING
    assert set(_US_STATES) >= _ISO_COLLIDING


def test_state_table_matches_prefilter(  # noqa: SLF001 — the point is to pin the duplication
) -> None:
    """`vja.location` and `vja.prefilter` are same-layer siblings, so neither can import the
    other's state table (import-linter). This is the guard against the two copies drifting."""
    assert set(_US_STATES) == set(prefilter._US_STATE_CODES.split())
    # `prefilter` lists the 50 state names; DC is carried there as a code only.
    names = {name.lower() for code, name in _US_STATES.items() if code != "DC"}
    assert names == set(prefilter._US_STATE_NAMES.split(","))
    assert len(_US_STATES) == 51
