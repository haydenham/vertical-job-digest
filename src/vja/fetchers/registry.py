"""Fetcher registry: an employer's `ats_type` → the fetcher that handles it.

Lets the pipeline turn an `Employer` row into "the right fetcher" without any
vertical- or company-specific branching (D-004). The Layer-1 deterministic ATSs are
wired here (Tier A + Workday + iCIMS/Jibe + Workable + SmartRecruiters + Oracle HCM); the
remaining Tier-C platforms and the Layer-2 LLM-read tail are handled by later blocks.
"""

from __future__ import annotations

from vja.fetchers.ashby import AshbyFetcher
from vja.fetchers.base import Fetcher
from vja.fetchers.greenhouse import GreenhouseFetcher
from vja.fetchers.icims import IcimsFetcher
from vja.fetchers.lever import LeverFetcher
from vja.fetchers.oracle import OracleFetcher
from vja.fetchers.smartrecruiters import SmartRecruitersFetcher
from vja.fetchers.workable import WorkableFetcher
from vja.fetchers.workday import WorkdayFetcher
from vja.models import AtsType

_FETCHERS: dict[AtsType, Fetcher] = {
    AtsType.GREENHOUSE: GreenhouseFetcher(),
    AtsType.LEVER: LeverFetcher(),
    AtsType.ASHBY: AshbyFetcher(),
    AtsType.WORKDAY: WorkdayFetcher(),
    AtsType.ICIMS: IcimsFetcher(),
    AtsType.WORKABLE: WorkableFetcher(),
    AtsType.SMARTRECRUITERS: SmartRecruitersFetcher(),
    AtsType.ORACLE_HCM: OracleFetcher(),
}

#: ATS types with a Layer-1 fetcher available (used to pre-filter fetchable employers).
SUPPORTED_ATS_TYPES: frozenset[AtsType] = frozenset(_FETCHERS)


def get_fetcher(ats_type: AtsType) -> Fetcher:
    """Return the fetcher for `ats_type`, or raise `ValueError` if none is wired.

    Callers should pre-filter to fetchable employers (see
    `vja.db.employers.active_fetchable_employers`), so a raise here means a routing bug.
    """
    try:
        return _FETCHERS[ats_type]
    except KeyError:
        raise ValueError(f"no Layer-1 fetcher for ats_type {ats_type.value!r}") from None
