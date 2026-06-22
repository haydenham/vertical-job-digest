"""Stage-B pre-filter (D-023): a cheap, deterministic gate over the *extracted* fields.

Stage A (`scope.py`) drops out-of-scope titles for free before any LLM cost. Stage B runs
*after* extraction (P5.2) on the structured fields and decides which in-scope postings are
worth spending the strong match model on for a given resume — the cost governor that bounds
matching spend (the strong model is the one real cost, D-005). Resume-aware refinement (does
this candidate actually fit) is the LLM's job in matching; Stage B only drops the obvious
non-matches (wrong level, wrong geo) the structured fields already settle.

Like Stage A this is **deliberately coarse** — it errs toward keeping (an `unknown` level or
location passes), because dropping a plausible match is worse than spending a few cents to let
the model rule it out. The knobs are vertical config (`prefilter` in `config/verticals/*.yaml`),
not code (D-004). Pure module: no DB, no I/O, no LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from vja.models import Level

# Concrete (non-`unknown`) career levels — a posting is dropped only when its level is one of
# these AND not in the vertical's allowed set. `unknown` is never a concrete level, so it passes.
_CONCRETE_LEVELS = frozenset(level.value for level in Level if level is not Level.UNKNOWN)

# US geo signals: the literal allowed tokens are added per-config; these are the always-on ones.
# `remote` passes (remote roles are geo-agnostic until the LLM reads the posting's fine print).
_US_SIGNALS = (
    "united states",
    "usa",
    "america",
    "remote",
)
# US state/DC signals — postal codes (matched whole-word so "in" won't hit "string") plus full
# names, since extraction may emit either form ("Houston, TX" or "Denver, Colorado"). Kept as raw
# strings split at use, so adding a state is a one-token edit.
_US_STATE_CODES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
    "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC"
)
_US_STATE_NAMES = (
    "alabama,alaska,arizona,arkansas,california,colorado,connecticut,delaware,florida,georgia,"
    "hawaii,idaho,illinois,indiana,iowa,kansas,kentucky,louisiana,maine,maryland,massachusetts,"
    "michigan,minnesota,mississippi,missouri,montana,nebraska,nevada,new hampshire,new jersey,"
    "new mexico,new york,north carolina,north dakota,ohio,oklahoma,oregon,pennsylvania,"
    "rhode island,south carolina,south dakota,tennessee,texas,utah,vermont,virginia,washington,"
    "west virginia,wisconsin,wyoming"
)
# Explicit non-US country signals (full names): naming one drops the location even when a US state
# CODE coincidentally collides (e.g. "Bengaluru, India, IN" — "IN" is also Indiana; "Cordoba,
# Argentina, AR" — "AR" is also Arkansas). Whole-word. Deliberately omits names that are also US
# places — "mexico" (New Mexico), "georgia" (the US state) — which lean on the absence of a US
# signal instead (e.g. "Mexico City, MX" has none). Bare ambiguous codes with no country name
# ("Munich, DE") stay a coarse-gate residual the location-aware match backstops.
_NON_US_COUNTRY_NAMES = (
    "india,china,japan,south korea,singapore,philippines,malaysia,thailand,vietnam,indonesia,"
    "pakistan,bangladesh,sri lanka,united kingdom,england,scotland,wales,ireland,france,germany,"
    "spain,portugal,italy,netherlands,belgium,switzerland,austria,sweden,norway,denmark,finland,"
    "poland,romania,hungary,greece,turkey,ukraine,russia,canada,mexico city,brazil,argentina,"
    "chile,colombia,peru,australia,new zealand,israel,united arab emirates,saudi arabia,"
    "south africa,egypt,nigeria,kenya"
)


@dataclass(frozen=True)
class PrefilterConfig:
    """The Stage-B knobs for a vertical (from `config/verticals/<key>.yaml`'s `prefilter`)."""

    locations: tuple[str, ...]
    levels: tuple[str, ...]


@lru_cache(maxsize=64)
def _location_matcher(allowed: tuple[str, ...]) -> re.Pattern[str]:
    """Whole-word, case-insensitive alternation of every US/allowed location signal (cached)."""
    tokens = [
        *_US_SIGNALS,
        *(loc.lower() for loc in allowed),
        *(code.lower() for code in _US_STATE_CODES.split()),
        *_US_STATE_NAMES.split(","),
    ]
    alternation = "|".join(re.escape(t) for t in tokens)
    return re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def _non_us_matcher() -> re.Pattern[str]:
    """Whole-word, case-insensitive alternation of explicit non-US country names (cached)."""
    alternation = "|".join(re.escape(name) for name in _NON_US_COUNTRY_NAMES.split(","))
    return re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE)


def _level_ok(level: str | None, cfg: PrefilterConfig) -> bool:
    """Drop only a *concrete* level outside the allowed set; `unknown`/null pass (coarse gate)."""
    if not level or level not in _CONCRETE_LEVELS:
        return True
    return level in cfg.levels


def _location_ok(location: str | None, cfg: PrefilterConfig) -> bool:
    """Keep null/unknown/remote/US locations; drop a location with no allowed signal at all.

    An explicit non-US country name drops the location even when a US state *code* coincidentally
    collides (e.g. "IN"=India/Indiana, "AR"=Argentina/Arkansas) — the foreign name wins.
    """
    if not location:
        return True
    if _non_us_matcher().search(location) is not None:
        return False
    return _location_matcher(cfg.locations).search(location) is not None


def passes_prefilter(level: str | None, location: str | None, cfg: PrefilterConfig) -> bool:
    """True iff a posting clears Stage B for `cfg` (so it earns the strong match model).

    Coarse by design: a posting is dropped only when its extracted fields *positively* place it
    out of range (a concrete senior/mid level, or a clearly non-US location). Unknown or absent
    fields pass — the LLM refines. `work_auth` is intentionally not gated here: the config carries
    no allowed values and the candidate's own auth status isn't encoded, so it's left for the
    matcher to weigh as a signal rather than dropped on.
    """
    return _level_ok(level, cfg) and _location_ok(location, cfg)
