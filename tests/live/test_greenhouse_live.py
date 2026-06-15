"""Opt-in live smoke for Greenhouse (D-019, docs/08 Level 4).

Excluded from the default run; invoke explicitly: ``uv run pytest -m live``.
Hits a real verified endpoint to catch ATS drift — it tests *Greenhouse's* response
shape (the keys `docs/05` maps), not our mapping logic (that's the offline unit test).
Run before a milestone or when drift is suspected, not per-commit.
"""

import pytest

from vja.fetchers.greenhouse import GreenhouseFetcher
from vja.models import AtsType, Employer


@pytest.mark.live
def test_greenhouse_camusenergy_shape_holds() -> None:
    employer = Employer(
        id=1,
        vertical="grid_power_software",
        name="Camus Energy",
        ats_type=AtsType.GREENHOUSE,
        ats_slug="camusenergy",
    )
    postings = GreenhouseFetcher().fetch(employer)

    assert postings, "expected at least one open posting from a verified board"
    sample = postings[0]
    assert sample.external_id
    assert sample.title
    assert sample.apply_url.startswith("http")
