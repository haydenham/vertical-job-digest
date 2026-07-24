"""Unit tests for `annual_usd_display` — the salary-display guard (F2 Phase A, D-087).

Pins the corroboration contract: the extracted integers render as a range only when the posting's
own compensation text agrees they are annual USD. Most cases below are **real production strings**
lifted from `postings.comp_raw` (with the integers Haiku actually stored for them), because the
whole reason this module exists is that the model does not honor "never annualize".
"""

from __future__ import annotations

import pytest

from vja.comp import annual_usd_display

# (comp_min, comp_max, comp_raw) exactly as observed in the dev DB — every one of these would have
# put a salary on the posting that the posting never offered.
REAL_FABRICATIONS = [
    # A ten-week internship paying $4,250/week, stored as a $170k salary.
    (170_000, 170_000, "$4,250 weekly base salary during the ten-week program"),
    (103_579, 125_258, "$49.82 to $60.22 per hour"),
    (80_000, 93_455, "Expected hourly rate between $38.46 to $44.95, varies based on experience"),
    # Canadian dollars stored as bare integers (note the typo in the source string).
    (75_000, 108_000, "75,000 CAD to 108,00 CAD"),
    # The compensation text quotes no figure at all — the integers came from somewhere else.
    (81_456, 122_184, "Pay within range listed + Bonus + Benefits + Equity"),
]

# Real strings that *are* corroborated annual USD, with the range they should format to.
REAL_ANNUAL = [
    (105_000, 131_325, "$105,000 and $131,325/year", "$105,000 – $131,325"),
    (84_800, 116_600, "$84,800.00/Yr. – $116,600.00/Yr.", "$84,800 – $116,600"),
    (58_000, 70_000, "between $58,000 - 70,000 USD", "$58,000 – $70,000"),
    (91_800, 124_200, "$91,800 - $124,200", "$91,800 – $124,200"),
    # Shorthand with no currency symbol at all: nothing contradicts annual USD, so it displays.
    (130_000, 175_000, "130 -175k", "$130,000 – $175,000"),
    # A range spanning two stated levels — the true span the posting quotes.
    (
        98_600,
        162_150,
        "Associate (Level 2): $98,600 - $133,400; Experienced (Level 3): $119,800",
        "$98,600 – $162,150",
    ),
]


@pytest.mark.parametrize(("comp_min", "comp_max", "comp_raw"), REAL_FABRICATIONS)
def test_real_production_fabrications_are_suppressed(
    comp_min: int, comp_max: int, comp_raw: str
) -> None:
    assert annual_usd_display(comp_min, comp_max, comp_raw) is None


@pytest.mark.parametrize(("comp_min", "comp_max", "comp_raw", "expected"), REAL_ANNUAL)
def test_real_annual_usd_strings_render(
    comp_min: int, comp_max: int, comp_raw: str, expected: str
) -> None:
    assert annual_usd_display(comp_min, comp_max, comp_raw) == expected


def test_no_integers_means_nothing_to_display() -> None:
    assert annual_usd_display(None, None, "$105,000 - $131,000 per year") is None


def test_missing_comp_raw_suppresses_even_well_formed_integers() -> None:
    # No corroborating text at all: the integers alone are exactly what we've learned not to trust.
    assert annual_usd_display(105_000, 131_000, None) is None
    assert annual_usd_display(105_000, 131_000, "   ") is None


def test_equal_bounds_render_as_a_single_figure() -> None:
    assert annual_usd_display(120_000, 120_000, "$120,000 per year") == "$120,000"


def test_single_sided_bounds() -> None:
    assert annual_usd_display(120_000, None, "$120,000 base") == "from $120,000"
    assert annual_usd_display(None, 150_000, "up to $150,000 annually") == "up to $150,000"


def test_inverted_range_is_suppressed_not_reordered() -> None:
    # A malformed extraction — we don't know which bound is wrong, so we claim neither.
    assert annual_usd_display(100_000, 90_000, "$100,000 - $90,000") is None


@pytest.mark.parametrize("comp_min", [50, 9_999, 2_000_001, 10_000_000])
def test_implausible_annual_figures_are_suppressed(comp_min: int) -> None:
    assert annual_usd_display(comp_min, None, "$50 - $60 stated in the posting") is None


def test_plausibility_band_is_inclusive_at_the_edges() -> None:
    assert annual_usd_display(10_000, 2_000_000, "$10,000 - $2,000,000") == "$10,000 – $2,000,000"


@pytest.mark.parametrize(
    "comp_raw",
    [
        "$60 per hour",
        "$60/hr",
        "$60 hourly",
        "480 daily",
        "$400 a day",
        "$2,000 weekly",
        "$2,000 biweekly",
        "$8,000 monthly",
        "paid quarterly, $30,000 per quarter",
        "$9,000 per semester",
    ],
)
def test_every_non_annual_period_suppresses(comp_raw: str) -> None:
    assert annual_usd_display(100_000, 130_000, comp_raw) is None


@pytest.mark.parametrize(
    "comp_raw",
    [
        "100,000 - 130,000 CAD",
        "€100,000 - €130,000",
        "£100,000 to £130,000",
        "zł144,000.00 - zł216,000.00",
        "₹8,000,000 per annum",
        "100,000 EUR",
        "R$ 400,000",
        "C$130,000",
    ],
)
def test_non_usd_currency_suppresses(comp_raw: str) -> None:
    assert annual_usd_display(100_000, 130_000, comp_raw) is None


def test_currency_codes_match_whole_words_only() -> None:
    # "Cadence" must not read as CAD, nor "Aedile"-style words as AED.
    result = annual_usd_display(100_000, 130_000, "$100,000 - $130,000; Cadence tools experience")
    assert result == "$100,000 – $130,000"


def test_ordinary_prose_dollar_is_not_a_prefixed_foreign_currency() -> None:
    # The R$/C$/A$ check requires the letter to actually price a number, so "for $100,000" is safe.
    assert annual_usd_display(100_000, None, "for $100,000 base") == "from $100,000"


def test_words_containing_a_period_marker_do_not_false_positive() -> None:
    # "through" contains "hr"; "Monday" contains "day" — neither is a pay period.
    result = annual_usd_display(100_000, 130_000, "$100,000 through $130,000, reviewed each Monday")
    assert result == "$100,000 – $130,000"


def test_annual_posting_that_merely_mentions_hours_is_suppressed() -> None:
    # Deliberate false negative: we can't tell "40-hour week" from an hourly quote cheaply, and
    # hiding a formatted range costs far less than inventing one. `comp_raw` still shows verbatim.
    assert (
        annual_usd_display(100_000, 130_000, "$100,000 - $130,000 for a 40-hour work week") is None
    )
