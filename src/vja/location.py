"""Render a posting's ATS location string in one consistent US form (D-106).

`postings.location` is whatever the board wrote and is **L1-authoritative** (D-043) — this module
never changes it. It answers a display question only: *what should a human read?* The same place
arrives four ways across employers, and a real slice of the corpus looks like this:

    Olathe, Kansas          Kinston, NC             USA - Seal Beach, CA
    Atlanta, Georgia        Atlanta, GA, United States      US, Dayton, OH
    Dallas, Texas           West Palm Beach, FL, US, 33407  Welch, MN, 55089

Sorting that column puts every Workday `USA - …` row under **U**, and filtering for a state finds
half the rows that match it. So: expand the state to its full name, strip the country affix and the
ZIP, and leave everything else alone.

**Expansion, not contraction, on purpose.** Going the other way (`Kansas` → `KS`) has to decide
whether `Georgia` is a state or a country and whether `Washington` is a state, a city, or DC.
Expanding a two-letter code can only ever face the reverse collision, which is narrower and, as
measured, rare.

The judgment calls follow `vja.comp`'s asymmetry: a wrong normalization *misstates a real posting's
location*, while a missed one merely leaves a string ugly. When a segment is ambiguous it is
returned verbatim.

Pure module: no DB, no I/O, no LLM. The `_US_STATES` table duplicates `vja.prefilter`'s state
tokens because same-layer siblings cannot import each other under import-linter; the duplication is
pinned by a test in `tests/unit/test_location.py`, not by a comment.
"""

from __future__ import annotations

import re
from functools import lru_cache

# Code → full name for the 50 states + DC. Kept as one table so the drift test can compare it
# against `prefilter`'s two token lists in a single assertion.
_US_STATES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

# `DC` is deliberately never expanded: "Washington, DC" is already the canonical rendering of that
# place, and "Washington, District of Columbia" reads as a mistake rather than a normalization.
_EXPANDABLE: dict[str, str] = {c: n for c, n in _US_STATES.items() if c != "DC"}

# State codes that are also ISO-3166 alpha-2 **country** codes, so "City, XX" is genuinely
# ambiguous ("Buenos Aires, AR"). These are the only codes that consult `_FOREIGN_CITIES` below.
_ISO_COLLIDING = frozenset(
    {
        "AL", "AR", "AZ", "CA", "CO", "DE", "GA", "ID", "IL", "IN", "KY", "LA", "MA", "MD",
        "ME", "MN", "MO", "MS", "MT", "NC", "NE", "PA", "SC", "SD", "TN", "VA",
    }
)  # fmt: skip

# The foreign cities that actually pair with a colliding code on these boards. Measured against the
# corpus, exactly three rows in 12,010 were at risk — `Gurugram, IN`, `Buenos Aires, AR`,
# `Bogota, CO` — because most countries these employers post from (UK, JP, MX, SG, BR, PH, CN, AU)
# carry codes that are not US states at all and never reach this check. The list is the observed
# cases plus their obvious near neighbours; an unlisted foreign city paired with its own country
# code still reads as a US state, which is the same coarse-gate residual `prefilter` documents for
# "Munich, DE". Adding a city is a one-token edit.
_FOREIGN_CITIES: dict[str, frozenset[str]] = {
    "AR": frozenset({"buenos aires", "cordoba", "córdoba", "rosario", "mendoza"}),
    "AZ": frozenset({"baku"}),
    "AL": frozenset({"tirana"}),
    "CA": frozenset(
        {
            "toronto",
            "montreal",
            "montréal",
            "vancouver",
            "ottawa",
            "calgary",
            "edmonton",
            "winnipeg",
            "mississauga",
            "quebec city",
            "halifax",
        }
    ),
    "CO": frozenset({"bogota", "bogotá", "medellin", "medellín", "cali", "barranquilla"}),
    "DE": frozenset(
        {
            "munich",
            "münchen",
            "berlin",
            "hamburg",
            "frankfurt",
            "stuttgart",
            "cologne",
            "köln",
            "düsseldorf",
            "dusseldorf",
            "leipzig",
            "dresden",
            "nuremberg",
            "hannover",
            "bremen",
        }
    ),
    "GA": frozenset({"libreville", "tbilisi"}),
    "ID": frozenset({"jakarta", "bandung", "surabaya"}),
    "IL": frozenset({"tel aviv", "jerusalem", "haifa", "herzliya", "ramat gan"}),
    "IN": frozenset(
        {
            "bengaluru",
            "bangalore",
            "hyderabad",
            "pune",
            "chennai",
            "mumbai",
            "delhi",
            "new delhi",
            "noida",
            "gurugram",
            "gurgaon",
            "kolkata",
            "ahmedabad",
            "jaipur",
            "coimbatore",
        }
    ),
    "KY": frozenset({"george town", "grand cayman"}),
    "LA": frozenset({"vientiane"}),
    "MA": frozenset({"casablanca", "rabat", "marrakech", "tangier"}),
    "MD": frozenset({"chisinau", "chișinău"}),
    "ME": frozenset({"podgorica"}),
    "MN": frozenset({"ulaanbaatar"}),
    "MO": frozenset({"macau", "macao"}),
    "MT": frozenset({"valletta"}),
    "NC": frozenset({"noumea", "nouméa"}),
    "NE": frozenset({"niamey"}),
    "PA": frozenset({"panama city"}),
    "SD": frozenset({"khartoum"}),
    "TN": frozenset({"tunis"}),
    "VA": frozenset({"vatican city"}),
}

# Non-US country names (mirrors `prefilter._NON_US_COUNTRY_NAMES`): naming one leaves the segment
# untouched, so "Bengaluru, Karnataka, India" and "Cordoba, Argentina, AR" are never rewritten.
# Same omissions for the same reason — "mexico" (New Mexico) and "georgia" (the state) would fire
# on US places, so they lean on the absence of a US signal instead.
_NON_US_COUNTRY_NAMES = (
    "india,china,japan,south korea,singapore,philippines,malaysia,thailand,vietnam,indonesia,"
    "pakistan,bangladesh,sri lanka,united kingdom,england,scotland,wales,ireland,france,germany,"
    "spain,portugal,italy,netherlands,belgium,switzerland,austria,sweden,norway,denmark,finland,"
    "poland,romania,hungary,greece,turkey,ukraine,russia,canada,mexico city,brazil,argentina,"
    "chile,colombia,peru,australia,new zealand,israel,united arab emirates,saudi arabia,"
    "south africa,egypt,nigeria,kenya"
)

# An explicit US mention anywhere in the raw string. It is the strongest corroboration available:
# with it, even an ISO-colliding code expands, and a space-separated trailing code ("Wilmington NC
# USA") is safe to rewrite. Matched on the ORIGINAL string, before any affix is stripped away.
_US_SIGNAL = re.compile(
    r"\b(?:usa|u\.s\.a\.|u\.s\.|us|united\s+states(?:\s+of\s+america)?)\b", re.IGNORECASE
)

# Country affixes, stripped from either end. Workday writes "USA - Seal Beach, CA"; Oracle writes
# "US, Dayton, OH"; Workable writes "Atlanta, GA, United States"; a few rows trail a bare " USA".
_LEADING_COUNTRY = re.compile(
    r"^(?:usa|us|u\.s\.a\.|u\.s\.|united\s+states(?:\s+of\s+america)?)\s*[-–—,]\s*", re.IGNORECASE
)
_TRAILING_COUNTRY = re.compile(
    r"\s*,\s*(?:usa|us|u\.s\.a\.|u\.s\.|united\s+states(?:\s+of\s+america)?)\s*$", re.IGNORECASE
)
_TRAILING_COUNTRY_BARE = re.compile(r"\s+(?:usa|u\.s\.a\.)\s*$", re.IGNORECASE)
# A trailing US ZIP, with or without its own comma segment ("…, FL, US, 33407"; "Welch, MN, 55089").
_TRAILING_ZIP = re.compile(r"\s*,?\s+\d{5}(?:-\d{4})?\s*$")
# A trailing space-separated state code, e.g. "Wilmington NC" once " USA" has been stripped.
_TRAILING_BARE_CODE = re.compile(r"^(?P<head>.*\S)\s+(?P<code>[A-Z]{2})$")

# Rippling joins a job's merged work locations with "; " (`fetchers/rippling.py`), and Workday's
# multi-site text arrives the same way — real rows run to fourteen segments.
_SEPARATOR = "; "


def us_location_display(location: str | None) -> str | None:
    """Return the normalized location, or `None` when there is nothing to improve.

    `None` means "render the stored `location` verbatim" — the caller's fallback, mirroring
    `vja.comp.annual_usd_display`. Returned for a null/blank input and for any string the rules
    leave unchanged, which keeps the field off the majority of rows in a list response.

    Each `"; "`-delimited segment is normalized independently and rejoined, so a multi-site posting
    is never collapsed into one place. Exactly duplicated segments are dropped (order preserved):
    two differently-written spellings of one office would otherwise normalize into a visible
    stutter. Never raises.
    """
    if not location or not location.strip():
        return None
    segments = [_normalize_segment(seg) for seg in location.split(";")]
    deduped: list[str] = []
    for segment in segments:
        if segment and segment not in deduped:
            deduped.append(segment)
    normalized = _SEPARATOR.join(deduped)
    return normalized if normalized and normalized != location else None


def _normalize_segment(segment: str) -> str:
    """Normalize one location segment: strip country affixes and ZIP, expand the state code."""
    text = " ".join(segment.split())
    if not text:
        return ""
    if _non_us_matcher().search(text) is not None:
        return text  # an explicit foreign country settles it — never rewrite
    us_signal = _US_SIGNAL.search(text) is not None
    text = _strip_affixes(text)
    return _expand_state(text, us_signal=us_signal) if text else ""


def _strip_affixes(text: str) -> str:
    """Peel country prefixes/suffixes and a trailing ZIP until the string stops shrinking.

    Repeated because they nest: "West Palm Beach, FL, US, 33407" needs the ZIP off before the
    country suffix is even at the end.
    """
    for _ in range(4):
        stripped = _TRAILING_ZIP.sub("", text)
        stripped = _TRAILING_COUNTRY.sub("", stripped)
        stripped = _TRAILING_COUNTRY_BARE.sub("", stripped)
        stripped = _LEADING_COUNTRY.sub("", stripped)
        stripped = stripped.strip().strip(",").strip()
        if stripped == text:
            break
        text = stripped
    return text


def _expand_state(text: str, *, us_signal: bool) -> str:
    """Expand a trailing US state code to its full name when the segment corroborates the US."""
    parts = [part.strip() for part in text.split(",")]
    code = parts[-1]
    if code in _EXPANDABLE and _may_expand(code, parts, us_signal=us_signal):
        parts[-1] = _EXPANDABLE[code]
        return ", ".join(parts)
    # "Wilmington NC" (from "Wilmington NC USA") — no comma to key on, so this is gated on the
    # explicit US mention alone. The rewrite inserts the comma the board omitted.
    if us_signal:
        match = _TRAILING_BARE_CODE.match(parts[-1])
        if match and match.group("code") in _EXPANDABLE:
            parts[-1] = f"{match.group('head')}, {_EXPANDABLE[match.group('code')]}"
            return ", ".join(parts)
    return text


def _may_expand(code: str, parts: list[str], *, us_signal: bool) -> bool:
    """Is this trailing code safe to read as a US state?

    Three tiers, cheapest first: an explicit US mention settles it; a code that is not also an ISO
    country code cannot be a country; otherwise the preceding segment must not name a known foreign
    city for that code. A bare code with nothing before it ("IN") stays a code.
    """
    if us_signal:
        return True
    if len(parts) < 2:
        return False
    if code not in _ISO_COLLIDING:
        return True
    city = parts[-2].strip().lower()
    return city not in _FOREIGN_CITIES.get(code, frozenset())


@lru_cache(maxsize=1)
def _non_us_matcher() -> re.Pattern[str]:
    """Whole-word, case-insensitive alternation of explicit non-US country names (cached)."""
    alternation = "|".join(re.escape(name) for name in _NON_US_COUNTRY_NAMES.split(","))
    return re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE)
