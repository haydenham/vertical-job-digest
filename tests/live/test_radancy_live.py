"""Opt-in live smoke for Radancy / TalentBrew (D-019, docs/08 Level 4).

Excluded from the default run; invoke with ``uv run pytest -m live -k radancy``. Hits a real
verified tenant (NextEra) to catch TalentBrew markup drift — it tests *Radancy's* HTML shape, not
our mapping logic (the offline fixture test does that). Run before a milestone.
"""

import pytest

from vja.fetchers.radancy import RadancyFetcher
from vja.models import AtsType, Employer


def _employer() -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="NextEra Energy",
        ats_type=AtsType.RADANCY,
        ats_slug=None,
        endpoint="https://jobs.nexteraenergy.com",
    )


@pytest.mark.live
def test_radancy_nextera_shape_holds() -> None:
    postings = RadancyFetcher().fetch(_employer())

    assert postings, "expected at least one open posting from a verified board"
    sample = postings[0]
    assert sample.external_id and "/" in sample.external_id  # "{slug}/{id}" path (the diff key)
    assert sample.title
    assert sample.apply_url.startswith("https://jobs.nexteraenergy.com/job/")
    assert sample.description is None  # list-only; description is the lazy detail fetch


@pytest.mark.live
def test_radancy_detail_has_description() -> None:
    fetcher = RadancyFetcher()
    sample = fetcher.fetch(_employer())[0]
    detail = fetcher.fetch_detail(_employer(), sample.external_id)
    assert detail["description"]  # the Layer-2 body
