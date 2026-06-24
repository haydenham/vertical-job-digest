"""Unit tests for endpoint construction (Chunk 4)."""

import pytest

from vja.fetchers.endpoints import build_endpoint
from vja.models import AtsType, Employer


def _employer(
    ats_type: AtsType, *, slug: str | None = None, endpoint: str | None = None
) -> Employer:
    return Employer(
        id=1,
        vertical="example_vertical",
        name="Example Co",
        ats_type=ats_type,
        ats_slug=slug,
        endpoint=endpoint,
    )


def test_greenhouse_url_is_derived_from_slug() -> None:
    url = build_endpoint(_employer(AtsType.GREENHOUSE, slug="camusenergy"))
    assert url == "https://boards-api.greenhouse.io/v1/boards/camusenergy/jobs?content=true"


def test_lever_url_is_derived_from_slug() -> None:
    url = build_endpoint(_employer(AtsType.LEVER, slug="voltus"))
    assert url == "https://api.lever.co/v0/postings/voltus?mode=json"


def test_ashby_url_is_derived_from_slug() -> None:
    url = build_endpoint(_employer(AtsType.ASHBY, slug="weave-grid"))
    assert url == "https://api.ashbyhq.com/posting-api/job-board/weave-grid"


def test_workable_url_is_derived_from_slug() -> None:
    url = build_endpoint(_employer(AtsType.WORKABLE, slug="vortexa"))
    assert url == "https://apply.workable.com/api/v1/widget/accounts/vortexa?details=true"


def test_smartrecruiters_url_is_derived_from_slug() -> None:
    # The limit/offset are added per-page by the fetcher, so the template is the bare list URL.
    url = build_endpoint(_employer(AtsType.SMARTRECRUITERS, slug="Vitol"))
    assert url == "https://api.smartrecruiters.com/v1/companies/Vitol/postings"


def test_derived_ats_without_slug_raises() -> None:
    with pytest.raises(ValueError, match="no ats_slug"):
        build_endpoint(_employer(AtsType.GREENHOUSE, slug=None))


def test_workday_uses_explicit_endpoint() -> None:
    endpoint = "https://vst.wd5.myworkdayjobs.com/wday/cxs/vst/vistra_careers/jobs"
    assert build_endpoint(_employer(AtsType.WORKDAY, endpoint=endpoint)) == endpoint


def test_non_derivable_without_endpoint_raises() -> None:
    with pytest.raises(ValueError, match="no explicit endpoint"):
        build_endpoint(_employer(AtsType.WORKDAY, endpoint=None))
