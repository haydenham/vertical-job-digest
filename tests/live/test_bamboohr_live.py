"""Opt-in live smoke for GridBeyond's public BambooHR careers API."""

import pytest

from vja.fetchers.bamboohr import BambooHRFetcher
from vja.models import AtsType, Employer


@pytest.mark.live
def test_bamboohr_gridbeyond_list_and_detail_shapes_hold() -> None:
    employer = Employer(
        id=1,
        vertical="grid_power_software",
        name="GridBeyond",
        ats_type=AtsType.BAMBOOHR,
        ats_slug="gridbeyond",
        careers_url="https://gridbeyond.bamboohr.com/careers/",
    )
    fetcher = BambooHRFetcher()
    postings = fetcher.fetch(employer)
    assert postings
    assert postings[0].external_id
    assert postings[0].apply_url.startswith("https://gridbeyond.bamboohr.com/careers/")
    detail = fetcher.fetch_detail(employer, postings[0].external_id)
    assert detail["description"]
    assert "formFields" not in detail
