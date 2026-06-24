"""Opt-in live smoke for SmartRecruiters (D-019, docs/08 Level 4).

Excluded from the default run; invoke with ``uv run pytest -m live -k smartrecruiters``. Hits a real
verified tenant (Vitol) to catch SmartRecruiters API drift — it tests *SmartRecruiters'* response
shape, not our mapping logic (the offline fixture test does that). Run before a milestone.
"""

import pytest

from vja.fetchers.smartrecruiters import SmartRecruitersFetcher
from vja.models import AtsType, Employer


def _employer() -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="Vitol",
        ats_type=AtsType.SMARTRECRUITERS,
        ats_slug="Vitol",
    )


@pytest.mark.live
def test_smartrecruiters_vitol_shape_holds() -> None:
    postings = SmartRecruitersFetcher().fetch(_employer())

    assert postings, "expected at least one open posting from a verified board"
    sample = postings[0]
    assert sample.external_id  # posting id (the diff key)
    assert sample.title
    assert sample.apply_url.startswith("https://jobs.smartrecruiters.com/Vitol/")
    assert sample.updated_at  # releasedDate, a real ISO date
    assert sample.description is None  # list-only; description is the lazy detail fetch


@pytest.mark.live
def test_smartrecruiters_detail_has_description() -> None:
    fetcher = SmartRecruitersFetcher()
    sample = fetcher.fetch(_employer())[0]
    detail = fetcher.fetch_detail(_employer(), sample.external_id)
    assert detail["jobAd"]["sections"]  # the Layer-2 body
