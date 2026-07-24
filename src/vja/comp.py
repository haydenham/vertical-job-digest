"""Decide whether a posting's extracted compensation is safe to render as a salary range (F2 A).

`postings.comp_min`/`comp_max` are *supposed* to be annual USD (the extraction prompt says so),
but the model does not honor that: production rows include `$49.82 to $60.22 per hour` stored as
`103579/125258`, a ten-week internship paying `$4,250 weekly` stored as `170000/170000`, and
`75,000 CAD to 108,00 CAD` stored as bare integers. Rendering those as "$170,000" would put a
salary on a real posting that the posting never offered — the same trust cost D-008 spends a whole
verification pass to avoid.

So the rule here is **corroboration, not trust**: the integers are displayed only when the
posting's own compensation text (`comp_raw`) agrees that they are annual USD figures. `comp_raw` is
the reliable anchor — in production it is never NULL while `comp_min` is set. Anything ambiguous
suppresses the numeric range, and the caller falls back to showing `comp_raw` verbatim, which is
always honest because it is the posting's own wording.

The asymmetry drives every judgment call: a false positive fabricates a salary, a false negative
merely hides a formatted range that the raw string still conveys. When in doubt, suppress.
"""

from __future__ import annotations

import re

# Words in `comp_raw` are matched by **prefix**, so "hour" also catches "hours"/"hourly". Their
# presence suppresses the range: the stored integers are then either an annualization the prompt
# forbids or unrelated to the quoted figure. Deliberately coarse — "40-hour work week" on a
# genuinely annual posting suppresses too, and that is the cheap direction to be wrong in.
_PERIOD_MARKERS = (
    "hour",
    "hr",
    "day",
    "daily",
    "week",
    "biweek",
    "month",
    "bimonth",
    "quarter",
    "semester",
)

# Non-USD currency codes, matched as whole words so "cadence" is not read as CAD.
_FOREIGN_CURRENCY_CODES = frozenset(
    {
        "cad",
        "eur",
        "gbp",
        "aud",
        "nzd",
        "inr",
        "sgd",
        "chf",
        "sek",
        "nok",
        "dkk",
        "pln",
        "mxn",
        "brl",
        "jpy",
        "cny",
        "rmb",
        "hkd",
        "zar",
        "ils",
        "aed",
    }
)

# Currency symbols that never occur inside an English word — a plain substring hit is conclusive.
_FOREIGN_CURRENCY_SYMBOLS = ("zł", "€", "£", "¥", "₹", "₽")

# The ambiguous "letter + $" currencies (R$ real, C$ / A$ dollars). A bare substring test would
# fire on ordinary prose ("for $105,000"), so require the symbol to actually price a number.
_PREFIXED_DOLLAR = re.compile(r"[rca]\$\s*\d")

_WORDS = re.compile(r"[a-z]+")

# Plausibility band for an annual US salary. Outside it, the integer is not an annual figure
# whatever `comp_raw` says (a stray hourly rate, a monthly stipend, a typo'd extra digit).
_MIN_PLAUSIBLE_ANNUAL = 10_000
_MAX_PLAUSIBLE_ANNUAL = 2_000_000


def annual_usd_display(
    comp_min: int | None,
    comp_max: int | None,
    comp_raw: str | None,
) -> str | None:
    """Format `comp_min`/`comp_max` as an annual-USD range, or `None` when it isn't safe to.

    Returns `None` — meaning "show `comp_raw` verbatim instead, or nothing" — whenever the
    corroboration rules below are not met. Never raises.

    Suppressed when: there is no integer at all; `comp_raw` is missing or carries no digits (no
    corroborating evidence, e.g. the real row "Pay within range listed + Bonus + Benefits +
    Equity" stored as `81456/122184`); `comp_raw` names a non-annual pay period or a non-USD
    currency; an integer falls outside the plausible annual band; or the range is inverted.
    """
    if comp_min is None and comp_max is None:
        return None
    if not _corroborates_annual_usd(comp_raw):
        return None
    for value in (comp_min, comp_max):
        if value is not None and not _MIN_PLAUSIBLE_ANNUAL <= value <= _MAX_PLAUSIBLE_ANNUAL:
            return None
    if comp_min is not None and comp_max is not None:
        if comp_min > comp_max:
            return None  # malformed extraction — don't guess which bound is right
        if comp_min == comp_max:
            return _dollars(comp_min)
        return f"{_dollars(comp_min)} – {_dollars(comp_max)}"
    if comp_min is not None:
        return f"from {_dollars(comp_min)}"
    return f"up to {_dollars(comp_max)}" if comp_max is not None else None


def _corroborates_annual_usd(comp_raw: str | None) -> bool:
    """Does the posting's own compensation text support reading the integers as annual USD?"""
    if comp_raw is None:
        return False
    text = comp_raw.strip().lower()
    if not text or not any(char.isdigit() for char in text):
        return False
    if any(symbol in text for symbol in _FOREIGN_CURRENCY_SYMBOLS):
        return False
    if _PREFIXED_DOLLAR.search(text):
        return False
    words = _WORDS.findall(text)
    if _FOREIGN_CURRENCY_CODES.intersection(words):
        return False
    return not any(word.startswith(_PERIOD_MARKERS) for word in words)


def _dollars(value: int) -> str:
    """Exact figure with thousands separators — the panel has the room, and rounding a bound
    either overstates the top of the range or understates the bottom."""
    return f"${value:,}"
