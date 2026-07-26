"""Opt-in live smoke for the public Rippling board contract."""

import pytest

from vja.fetchers.rippling import RipplingFetcher
from vja.models import AtsType, Employer


def _employer(name: str, slug: str) -> Employer:
    return Employer(
        id=0,
        vertical="grid_power_software",
        name=name,
        ats_type=AtsType.RIPPLING,
        ats_slug=slug,
    )


@pytest.mark.live
@pytest.mark.parametrize(
    "name, slug",
    [("Gridsight", "gridsight"), ("Portside", "portside"), ("Raptor Maps", "raptor-maps-inc")],
)
def test_board_returns_postings_with_supplied_apply_links(name: str, slug: str) -> None:
    postings = RipplingFetcher().fetch(_employer(name, slug))

    assert postings
    assert all(posting.external_id and posting.title and posting.apply_url for posting in postings)
    assert all("ats.rippling.com" in posting.apply_url for posting in postings)
    # List-only: the body is never in the list response (D-050).
    assert all(posting.description is None for posting in postings)


@pytest.mark.live
def test_detail_carries_the_split_body_the_list_omits() -> None:
    fetcher = RipplingFetcher()
    employer = _employer("Gridsight", "gridsight")

    posting = fetcher.fetch(employer)[0]
    detail = fetcher.fetch_detail(employer, posting.external_id)
    body = fetcher.detail_description(detail)

    assert set(detail["description"]) >= {"company", "role"}
    assert body
    # `role` leads (D-095 display order), so the boilerplate never opens the panel.
    assert body.startswith(detail["description"]["role"].strip()[:40])
