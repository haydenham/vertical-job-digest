"""Opt-in live smoke for the public Pinpoint postings contract."""

import pytest

from vja.fetchers.pinpoint import PinpointFetcher
from vja.models import AtsType, Employer


@pytest.mark.live
def test_aireon_board_returns_postings_with_apply_links() -> None:
    employer = Employer(
        id=0,
        vertical="aviation_software",
        name="Aireon",
        ats_type=AtsType.PINPOINT,
        ats_slug="aireon",
        careers_url="https://aireon.com/about/careers/",
    )

    postings = PinpointFetcher().fetch(employer)

    assert postings
    assert all(posting.external_id and posting.title and posting.apply_url for posting in postings)
    assert all("pinpointhq.com" in posting.apply_url for posting in postings)
