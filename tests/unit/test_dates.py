"""Unit tests for `normalize_ats_date` (A1, D-038).

Pins the tolerant contract: every ATS date shape collapses to tz-aware UTC, and anything
unparseable (incl. the parked DRW malformed-`posted_at` case) returns None rather than raising.
"""

from datetime import UTC, datetime

import pytest

from vja.dates import normalize_ats_date


def test_iso_with_offset_converts_to_utc() -> None:
    # Greenhouse-style ISO 8601 with a timezone offset.
    result = normalize_ats_date("2026-06-15T08:30:00-04:00")
    assert result == datetime(2026, 6, 15, 12, 30, 0, tzinfo=UTC)
    assert result is not None and result.tzinfo is UTC


def test_iso_zulu_suffix() -> None:
    assert normalize_ats_date("2026-06-15T12:30:00Z") == datetime(2026, 6, 15, 12, 30, tzinfo=UTC)


def test_naive_iso_assumed_utc() -> None:
    # Ashby `publishedAt` is usually offset-aware, but a naive value must not crash — assume UTC.
    result = normalize_ats_date("2026-06-15T12:30:00")
    assert result == datetime(2026, 6, 15, 12, 30, tzinfo=UTC)


def test_date_only_is_midnight_utc() -> None:
    assert normalize_ats_date("2026-06-15") == datetime(2026, 6, 15, 0, 0, tzinfo=UTC)


def test_lever_epoch_millis_string() -> None:
    # Lever `createdAt` is epoch-millis serialized to a string.
    # 1_750_000_000_000 ms == 2025-06-15T14:13:20Z.
    assert normalize_ats_date("1750000000000") == datetime.fromtimestamp(1_750_000_000, tz=UTC)


def test_epoch_seconds_string() -> None:
    assert normalize_ats_date("1750000000") == datetime.fromtimestamp(1_750_000_000, tz=UTC)


@pytest.mark.parametrize(
    "value",
    [
        "2026",  # a bare year — must NOT become epoch-seconds 1970 (the wart this guards)
        "202606",
        "0",
        "99999999999",  # large-but-sub-threshold → would land in the year ~5138
        "100000000000",  # at the ms threshold but /1000 lands in 1973
    ],
)
def test_implausible_epoch_returns_none(value: str) -> None:
    # A digit string is only trusted as an epoch when it resolves to a posting-era date;
    # otherwise None (which falls back to first_seen_at) beats a silently-garbage date.
    assert normalize_ats_date(value) is None


def test_surrounding_whitespace_is_trimmed() -> None:
    assert normalize_ats_date("  2026-06-15T12:30:00Z  ") == datetime(
        2026, 6, 15, 12, 30, tzinfo=UTC
    )


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_returns_none(value: str | None) -> None:
    assert normalize_ats_date(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "Posted 2 Days Ago",  # Workday's relative string
        "January 2026",
        "2026-13-99",  # impossible date
        "not a date",
        "n/a",
    ],
)
def test_malformed_returns_none(value: str) -> None:
    # The DRW regression: a malformed extracted date must normalize to None, never raise.
    assert normalize_ats_date(value) is None
