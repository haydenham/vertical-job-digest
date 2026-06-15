"""Unit tests for the domain models + the Fetcher contract (Chunk 2).

Pins the contract everything else builds on: `RawPosting`/`Employer` are immutable
value objects, the schema enums carry the exact string values the DB stores, and a
conforming class satisfies the `Fetcher` Protocol.
"""

import dataclasses

import pytest

from vja.fetchers.base import Fetcher, FetchError
from vja.models import AtsType, Employer, Level, RawPosting, RemoteType, Verdict


def test_rawposting_construction_maps_fields() -> None:
    p = RawPosting(
        external_id="123",
        title="Software Engineer",
        apply_url="https://example.com/apply/123",
        location="Austin, TX",
        updated_at="2026-06-15T00:00:00Z",
        raw={"id": 123},
    )
    assert p.external_id == "123"
    assert p.title == "Software Engineer"
    assert p.apply_url == "https://example.com/apply/123"
    assert p.location == "Austin, TX"
    assert p.updated_at == "2026-06-15T00:00:00Z"
    assert p.raw == {"id": 123}


def test_rawposting_optional_fields_accept_none() -> None:
    p = RawPosting(
        external_id="1",
        title="Engineer",
        apply_url="https://example.com/1",
        location=None,
        updated_at=None,
        raw={},
    )
    assert p.location is None
    assert p.updated_at is None


def test_rawposting_is_frozen() -> None:
    p = RawPosting(
        external_id="1",
        title="Engineer",
        apply_url="https://example.com/1",
        location=None,
        updated_at=None,
        raw={},
    )
    attr = "title"  # via a variable so this isn't a literal-setattr lint (B010)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(p, attr, "changed")


def test_employer_is_frozen_and_defaults_optional_fields() -> None:
    e = Employer(
        id=1,
        vertical="example_vertical",
        name="Example Co",
        ats_type=AtsType.GREENHOUSE,
    )
    assert e.ats_slug is None
    assert e.endpoint is None
    assert e.careers_url is None
    attr = "name"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(e, attr, "Other")


def test_enum_values_are_the_exact_db_strings() -> None:
    # `.value` is the exact string the DB persists (StrEnum member == its value).
    assert AtsType.GREENHOUSE.value == "greenhouse"
    assert AtsType.ORACLE_HCM.value == "oracle_hcm"
    assert Level.NEW_GRAD.value == "new_grad"
    assert RemoteType.REMOTE.value == "remote"
    assert Verdict.STRONG_YES.value == "strong_yes"
    # Lookup by value round-trips to the member (used when importing the seed CSV).
    assert AtsType("workday") is AtsType.WORKDAY


def test_fetcher_protocol_satisfied_by_conforming_class() -> None:
    class DummyFetcher:
        ats_type = AtsType.GREENHOUSE

        def fetch(self, employer: Employer) -> list[RawPosting]:
            return []

    assert isinstance(DummyFetcher(), Fetcher)


def test_fetcherror_is_an_exception() -> None:
    assert issubclass(FetchError, Exception)
