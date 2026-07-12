"""Opt-in live smoke for United's public Phenom widget API (D-076/D-019)."""

import pytest

from vja.fetchers.phenom import PhenomFetcher
from vja.models import AtsType, Employer


@pytest.mark.live
def test_phenom_united_list_and_detail_shapes_hold() -> None:
    employer = Employer(
        id=1,
        vertical="aviation_software",
        name="United Airlines",
        ats_type=AtsType.PHENOM,
        endpoint="https://careers.united.com?lang=en_us&country=us",
        careers_url="https://careers.united.com/",
    )
    fetcher = PhenomFetcher()
    postings = fetcher.fetch(employer)
    assert postings
    assert postings[0].external_id
    assert postings[0].apply_url.startswith("https://")
    detail = fetcher.fetch_detail(employer, postings[0].external_id)
    assert detail["description"]
