"""Normalize the assorted ATS date strings into one tz-aware UTC datetime (A1, D-038).

Layer-1 fetchers and Layer-2 extraction hand us dates in incompatible shapes — ISO 8601
(Greenhouse `updated_at`, Ashby `publishedAt`), epoch-millis strings (Lever `createdAt`), the
LLM's best-effort `posted_at` string, or nothing at all (Workday's list). `normalize_ats_date`
collapses all of them to a single `datetime | None` so `postings.source_updated_at` can be a real,
queryable timestamp (the D-030 dashboard windows + the D-024 backfill cap read it).

The contract is **tolerant**: anything unparseable returns `None` rather than raising — a posting
must never fail to persist because an ATS (or the extraction model) emitted a malformed date. This
is also where the parked DRW malformed-`posted_at` row (D-035) stops being a problem: it normalizes
to `None` and falls back to `first_seen_at` downstream.
"""

from __future__ import annotations

from datetime import UTC, datetime

# A pure-digit epoch at/above this is milliseconds (~ Mar 2001 in ms); below it, seconds.
# Lever emits epoch-millis; the threshold lets us also accept a plain epoch-seconds string.
_EPOCH_MS_THRESHOLD = 100_000_000_000  # 1e11

# A digit string is only believable as an epoch if it lands in this posting-era window.
# Guards against a bare year ("2026" → epoch-seconds → 1970) or a too-short/too-long number
# producing a garbage date — which is worse than None (None falls back to `first_seen_at`).
_MIN_YEAR = 2000
_MAX_YEAR = 2100


def normalize_ats_date(value: str | None) -> datetime | None:
    """Parse an ATS/LLM date string into a tz-aware UTC `datetime`, or `None` if unparseable.

    Accepts ISO 8601 (with offset, `Z`, or date-only — assumed UTC when naive) and epoch
    seconds/milliseconds given as a digit string. Never raises; unknown formats → `None`.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    if text.isdigit():
        return _from_epoch(text)
    return _from_iso(text)


def _from_epoch(digits: str) -> datetime | None:
    try:
        number = int(digits)
    except ValueError:  # pragma: no cover - guarded by isdigit()
        return None
    seconds = number / 1000 if number >= _EPOCH_MS_THRESHOLD else number
    try:
        parsed = datetime.fromtimestamp(seconds, tz=UTC)
    except (ValueError, OverflowError, OSError):
        return None
    if not _MIN_YEAR <= parsed.year <= _MAX_YEAR:
        return None  # not a believable epoch (e.g. a bare year) — prefer None over a garbage date
    return parsed


def _from_iso(text: str) -> datetime | None:
    # `fromisoformat` (py3.11+) accepts offsets, a trailing `Z`, and date-only strings.
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # Naive ISO (no offset, or a bare date) is assumed UTC; aware values convert to UTC.
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
