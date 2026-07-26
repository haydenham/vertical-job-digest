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


def test_bamboohr_url_is_derived_from_slug() -> None:
    url = build_endpoint(_employer(AtsType.BAMBOOHR, slug="gridbeyond"))
    assert url == "https://gridbeyond.bamboohr.com/careers/list"


def test_pinpoint_url_is_derived_from_slug() -> None:
    url = build_endpoint(_employer(AtsType.PINPOINT, slug="aireon"))
    assert url == "https://aireon.pinpointhq.com/postings.json"


def test_rippling_url_is_derived_from_slug() -> None:
    url = build_endpoint(_employer(AtsType.RIPPLING, slug="gridsight"))
    assert url == "https://api.rippling.com/platform/api/ats/v1/board/gridsight/jobs"


def test_rippling_redundant_endpoint_does_not_override_the_canonical_host() -> None:
    # The custom-domain override stays scoped to Pinpoint (D-079): every Rippling board this
    # audit found lives on the one canonical API host, and a stale `ats.rippling.com` page URL
    # in an employer row must not be fetched in place of the JSON endpoint.
    employer = _employer(
        AtsType.RIPPLING, slug="gridsight", endpoint="https://ats.rippling.com/gridsight/jobs"
    )
    assert build_endpoint(employer) == (
        "https://api.rippling.com/platform/api/ats/v1/board/gridsight/jobs"
    )


def test_explicit_endpoint_overrides_derived_url_for_custom_domain() -> None:
    endpoint = "https://careers.auroraer.com/postings.json"
    employer = _employer(AtsType.PINPOINT, endpoint=endpoint)
    assert build_endpoint(employer) == endpoint


def test_redundant_endpoint_does_not_override_existing_derived_provider() -> None:
    employer = _employer(
        AtsType.GREENHOUSE,
        slug="camusenergy",
        endpoint="https://boards-api.greenhouse.io/v1/boards/camusenergy/jobs",
    )
    assert build_endpoint(employer).endswith("/jobs?content=true")


def test_derived_ats_without_slug_raises() -> None:
    with pytest.raises(ValueError, match="no ats_slug"):
        build_endpoint(_employer(AtsType.GREENHOUSE, slug=None))


def test_workday_uses_explicit_endpoint() -> None:
    endpoint = "https://vst.wd5.myworkdayjobs.com/wday/cxs/vst/vistra_careers/jobs"
    assert build_endpoint(_employer(AtsType.WORKDAY, endpoint=endpoint)) == endpoint


def test_paylocity_uses_explicit_endpoint() -> None:
    endpoint = "https://recruiting.paylocity.com/recruiting/jobs/All/uuid/company"
    assert build_endpoint(_employer(AtsType.PAYLOCITY, endpoint=endpoint)) == endpoint


def test_phenom_uses_explicit_endpoint_with_tenant_query() -> None:
    endpoint = "https://careers.test.com?lang=en_us&country=us"
    assert build_endpoint(_employer(AtsType.PHENOM, endpoint=endpoint)) == endpoint


def test_non_derivable_without_endpoint_raises() -> None:
    with pytest.raises(ValueError, match="no explicit endpoint"):
        build_endpoint(_employer(AtsType.WORKDAY, endpoint=None))
