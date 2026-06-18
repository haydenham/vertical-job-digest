"""Stage-A scope gate (D-023): a free, deterministic, resume-independent title filter.

Runs on the fetched **title** before any LLM work, so out-of-scope roles (senior, non-software,
wrong function) never cost a token. Resume-aware geo/level refinement happens later in Stage B
(post-extraction). The gate is *balanced*: keep a title iff it matches at least one `role_include`
keyword AND matches no `exclude` keyword. Matching is whole-word and case-insensitive (so `ml`
won't match "html", and `sr` matches "Sr." but not "disregard"). Keyword lists are vertical config
(`config/verticals/*.yaml`), not code — tune without a code change (D-004).

Pure module: no DB, no I/O. Phase 5.1 ships the function + config; 5.2 consumes it when choosing
which postings to extract. Postings are never dropped from the DB (the diff still tracks them all).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class ScopeConfig:
    """The Stage-A keyword lists for a vertical (from `config/verticals/<key>.yaml`)."""

    role_include: tuple[str, ...]
    exclude: tuple[str, ...]


@lru_cache(maxsize=64)
def _matcher(keywords: tuple[str, ...]) -> re.Pattern[str] | None:
    """A compiled whole-word, case-insensitive alternation over `keywords` (cached by tuple)."""
    if not keywords:
        return None
    alternation = "|".join(re.escape(k.lower()) for k in keywords)
    return re.compile(rf"\b(?:{alternation})\b")


def in_scope(title: str | None, scope: ScopeConfig) -> bool:
    """True iff `title` looks in-scope for the vertical (role match AND no exclude match)."""
    if not title:
        return False
    text = title.lower()
    include = _matcher(scope.role_include)
    exclude = _matcher(scope.exclude)
    has_role = include is not None and include.search(text) is not None
    has_exclude = exclude is not None and exclude.search(text) is not None
    return has_role and not has_exclude
