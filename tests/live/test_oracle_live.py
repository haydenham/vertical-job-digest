"""Opt-in live smoke for Oracle HCM / ORC (D-019, docs/08 Level 4).

Excluded from the default run; invoke with ``uv run pytest -m live -k oracle``. Hits a real verified
tenant (Southern Company) to catch Oracle Candidate-Experience API drift — it tests *Oracle's*
response shape, not our mapping logic (the offline fixture test does that). Run before a milestone.
"""

import pytest

from vja.fetchers.oracle import OracleFetcher
from vja.models import AtsType, Employer

_HOST = "https://emje.fa.us6.oraclecloud.com"


def _employer() -> Employer:
    return Employer(
        id=1,
        vertical="grid_power_software",
        name="Southern Company",
        ats_type=AtsType.ORACLE_HCM,
        endpoint=(
            f"{_HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            "?onlyData=true&expand=requisitionList.secondaryLocations"
            "&finder=findReqs;siteNumber=CX_1001"
        ),
        careers_url=f"{_HOST}/hcmUI/CandidateExperience/en/sites/SouthernCompanyJobs",
    )


@pytest.mark.live
def test_oracle_southern_shape_holds() -> None:
    postings = OracleFetcher().fetch(_employer())

    assert postings, "expected at least one open posting from a verified board"
    sample = postings[0]
    assert sample.external_id  # requisition Id (the diff key)
    assert sample.title
    assert sample.apply_url.startswith(f"{_HOST}/hcmUI/CandidateExperience")
    assert sample.updated_at  # PostedDate
    assert sample.description is None  # list-only; description is the lazy detail fetch


@pytest.mark.live
def test_oracle_detail_has_description() -> None:
    fetcher = OracleFetcher()
    sample = fetcher.fetch(_employer())[0]
    detail = fetcher.fetch_detail(_employer(), sample.external_id)
    assert detail.get("ExternalDescriptionStr")  # the Layer-2 body
