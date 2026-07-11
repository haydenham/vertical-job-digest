"""Opt-in live smoke for the public Paylocity Recruiting board (D-076/D-019)."""

import pytest

from vja.fetchers.paylocity import PaylocityFetcher
from vja.models import AtsType, Employer


@pytest.mark.live
def test_paylocity_veryon_shape_holds() -> None:
    employer = Employer(
        id=1,
        vertical="aviation_software",
        name="Veryon",
        ats_type=AtsType.PAYLOCITY,
        endpoint=(
            "https://recruiting.paylocity.com/recruiting/jobs/All/"
            "eaf316dd-b54d-49a6-b1d8-1ab594e6a319/Veryon"
        ),
    )
    postings = PaylocityFetcher().fetch(employer)
    assert postings
    assert postings[0].external_id.isdigit()
    assert postings[0].apply_url.startswith(
        "https://recruiting.paylocity.com/Recruiting/jobs/Apply/"
    )
    detail = PaylocityFetcher().fetch_detail(employer, postings[0].external_id)
    assert detail["description"], "expected a description on the public detail page"
