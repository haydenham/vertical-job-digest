"""Opt-in live smoke for Workable (D-019, docs/08 Level 4).

Excluded from the default run; invoke with ``uv run pytest -m live -k workable``. Hits a real
verified tenant (Vortexa) to catch Workable embed-widget drift — it tests *Workable's* response
shape, not our mapping logic (the offline fixture test does that). Run before a milestone.
"""

import pytest

from vja.fetchers.workable import WorkableFetcher
from vja.models import AtsType, Employer


@pytest.mark.live
def test_workable_vortexa_shape_holds() -> None:
    employer = Employer(
        id=1,
        vertical="grid_power_software",
        name="Vortexa",
        ats_type=AtsType.WORKABLE,
        ats_slug="vortexa",
    )
    postings = WorkableFetcher().fetch(employer)

    assert postings, "expected at least one open posting from a verified board"
    sample = postings[0]
    assert sample.external_id  # shortcode
    assert sample.title
    assert sample.apply_url.startswith("https://")
    assert sample.updated_at  # Workable gives a real ISO date
