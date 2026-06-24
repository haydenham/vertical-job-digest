"""Opt-in live smoke for iCIMS (Jibe Career Sites) (D-019, docs/08 Level 4).

Excluded from the default run; invoke with ``uv run pytest -m live -k icims``. Hits a real
verified tenant (Garmin) to catch Jibe `/api/jobs` drift — it tests *iCIMS's* response shape,
not our mapping logic (the offline fixture test does that). Run before a milestone.
"""

import pytest

from vja.fetchers.icims import IcimsFetcher
from vja.models import AtsType, Employer


@pytest.mark.live
def test_icims_garmin_shape_holds() -> None:
    employer = Employer(
        id=1,
        vertical="aviation_software",
        name="Garmin",
        ats_type=AtsType.ICIMS,
        ats_slug="garmin",
        endpoint="https://careers.garmin.com/api/jobs",
    )
    postings = IcimsFetcher().fetch(employer)

    assert postings, "expected at least one open posting from a verified board"
    sample = postings[0]
    assert sample.external_id  # req_id
    assert sample.title
    assert sample.apply_url.startswith("https://")
    assert sample.updated_at  # Jibe gives a real ISO date
