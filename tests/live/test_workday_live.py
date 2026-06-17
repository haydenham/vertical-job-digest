"""Opt-in live smoke for Workday cxs (P4B1, D-019, docs/08 Level 4).

Excluded from the default run; invoke with ``uv run pytest -m live -k workday``. Hits a real
verified tenant (PJM, a small board) to catch cxs drift — it tests *Workday's* response shape,
not our mapping logic (the offline fixture test does that). Run before a milestone.
"""

import pytest

from vja.fetchers.workday import WorkdayFetcher
from vja.models import AtsType, Employer


@pytest.mark.live
def test_workday_pjm_shape_holds() -> None:
    employer = Employer(
        id=1,
        vertical="grid_power_software",
        name="PJM Interconnection",
        ats_type=AtsType.WORKDAY,
        ats_slug="pjm:wd5:pjmcareers",
        endpoint="https://pjm.wd5.myworkdayjobs.com/wday/cxs/pjm/pjmcareers/jobs",
    )
    postings = WorkdayFetcher().fetch(employer)

    assert postings, "expected at least one open posting from a verified board"
    sample = postings[0]
    assert sample.external_id.startswith("/")  # externalPath
    assert sample.title
    assert sample.apply_url.startswith("https://pjm.wd5.myworkdayjobs.com/pjmcareers/")
