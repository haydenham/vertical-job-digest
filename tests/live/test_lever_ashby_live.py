"""Opt-in live smoke for Lever + Ashby (D-019, docs/08 Level 4).

Excluded from the default run; invoke with ``uv run pytest -m live``. Hits real
verified endpoints to catch ATS drift — tests *their* response shape, not our mapping.
"""

import pytest

from vja.fetchers.ashby import AshbyFetcher
from vja.fetchers.lever import LeverFetcher
from vja.models import AtsType, Employer


@pytest.mark.live
def test_lever_voltus_shape_holds() -> None:
    employer = Employer(
        id=1,
        vertical="grid_power_software",
        name="Voltus",
        ats_type=AtsType.LEVER,
        ats_slug="voltus",
    )
    postings = LeverFetcher().fetch(employer)
    assert postings, "expected at least one open posting from a verified board"
    sample = postings[0]
    assert sample.external_id
    assert sample.title
    assert sample.apply_url.startswith("http")


@pytest.mark.live
def test_ashby_weavegrid_shape_holds() -> None:
    employer = Employer(
        id=1,
        vertical="grid_power_software",
        name="WeaveGrid",
        ats_type=AtsType.ASHBY,
        ats_slug="weave-grid",
    )
    postings = AshbyFetcher().fetch(employer)
    assert postings, "expected at least one open posting from a verified board"
    sample = postings[0]
    assert sample.external_id
    assert sample.title
    assert sample.apply_url.startswith("http")
