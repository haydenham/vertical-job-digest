"""Endpoint construction: an `Employer` row → the URL to fetch (`docs/05`).

For the clean JSON ATSs (Greenhouse/Lever/Ashby) the URL is *derived* from
`ats_slug`, so the seed CSV can leave `endpoint` blank. For Workday (and other
hand-configured platforms) the per-company `endpoint` column is the source of truth.
Kept separate from the HTTP fetchers so it stays a pure, exhaustively-tested function.
"""

from __future__ import annotations

from vja.models import AtsType, Employer

# ATSs whose endpoint is derived from the slug alone (GH/Lever/Ashby verified live
# 2026-06-11; Workable's embed-widget API + SmartRecruiters' public postings API verified
# live 2026-06-24 — Workable's `?details=true` is required for the inline description;
# SmartRecruiters' limit/offset are added per-page by the fetcher, so the template is bare;
# BambooHR and Pinpoint expose slug-derived public careers APIs; an explicit endpoint
# remains authoritative for custom-domain boards such as Aurora Energy Research's Pinpoint site;
# Rippling's board API is one canonical host keyed by slug, verified live 2026-07-26).
_DERIVED_TEMPLATES: dict[AtsType, str] = {
    AtsType.GREENHOUSE: "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    AtsType.LEVER: "https://api.lever.co/v0/postings/{slug}?mode=json",
    AtsType.ASHBY: "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    AtsType.WORKABLE: "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true",
    AtsType.SMARTRECRUITERS: "https://api.smartrecruiters.com/v1/companies/{slug}/postings",
    AtsType.BAMBOOHR: "https://{slug}.bamboohr.com/careers/list",
    AtsType.PINPOINT: "https://{slug}.pinpointhq.com/postings.json",
    AtsType.RIPPLING: "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs",
}


def build_endpoint(employer: Employer) -> str:
    """Return the fetch URL for `employer`, or raise `ValueError` if it can't be built.

    A `ValueError` here is a *configuration* defect (a misfiled seed row), distinct
    from a runtime `FetchError` (the network/parse failures a fetcher raises). Both
    are loud; neither is swallowed.
    """
    # Pinpoint alone has a verified provider-backed custom-domain contract. Keep the
    # override scoped: older derived-provider seed rows carry redundant endpoints that
    # intentionally omit required query options such as Greenhouse's `content=true`.
    if employer.ats_type is AtsType.PINPOINT and employer.endpoint:
        return employer.endpoint

    template = _DERIVED_TEMPLATES.get(employer.ats_type)
    if template is not None:
        if not employer.ats_slug:
            raise ValueError(
                f"{employer.ats_type.value} employer {employer.name!r} has no ats_slug "
                "to build an endpoint from"
            )
        return template.format(slug=employer.ats_slug)

    # Workday + other hand-configured platforms: the explicit endpoint is authoritative.
    if employer.endpoint:
        return employer.endpoint

    raise ValueError(
        f"cannot build endpoint for {employer.name!r}: ats_type {employer.ats_type.value!r} "
        "is not slug-derivable and no explicit endpoint is set"
    )
