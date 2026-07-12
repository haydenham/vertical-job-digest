"""Unit tests for the fetcher registry (Block 2)."""

import pytest

from vja.fetchers.ashby import AshbyFetcher
from vja.fetchers.bamboohr import BambooHRFetcher
from vja.fetchers.greenhouse import GreenhouseFetcher
from vja.fetchers.icims import IcimsFetcher
from vja.fetchers.lever import LeverFetcher
from vja.fetchers.oracle import OracleFetcher
from vja.fetchers.paylocity import PaylocityFetcher
from vja.fetchers.phenom import PhenomFetcher
from vja.fetchers.radancy import RadancyFetcher
from vja.fetchers.registry import SUPPORTED_ATS_TYPES, get_fetcher
from vja.fetchers.smartrecruiters import SmartRecruitersFetcher
from vja.fetchers.workable import WorkableFetcher
from vja.fetchers.workday import WorkdayFetcher
from vja.models import AtsType


def test_each_layer1_ats_maps_to_its_fetcher() -> None:
    assert isinstance(get_fetcher(AtsType.GREENHOUSE), GreenhouseFetcher)
    assert isinstance(get_fetcher(AtsType.LEVER), LeverFetcher)
    assert isinstance(get_fetcher(AtsType.ASHBY), AshbyFetcher)
    assert isinstance(get_fetcher(AtsType.WORKDAY), WorkdayFetcher)
    assert isinstance(get_fetcher(AtsType.ICIMS), IcimsFetcher)
    assert isinstance(get_fetcher(AtsType.WORKABLE), WorkableFetcher)
    assert isinstance(get_fetcher(AtsType.SMARTRECRUITERS), SmartRecruitersFetcher)
    assert isinstance(get_fetcher(AtsType.ORACLE_HCM), OracleFetcher)
    assert isinstance(get_fetcher(AtsType.RADANCY), RadancyFetcher)
    assert isinstance(get_fetcher(AtsType.PAYLOCITY), PaylocityFetcher)
    assert isinstance(get_fetcher(AtsType.PHENOM), PhenomFetcher)
    assert isinstance(get_fetcher(AtsType.BAMBOOHR), BambooHRFetcher)


def test_returned_fetcher_reports_matching_ats_type() -> None:
    for ats in SUPPORTED_ATS_TYPES:
        assert get_fetcher(ats).ats_type == ats


def test_unsupported_ats_type_raises() -> None:
    # Jobvite is a known ATS but has no Layer-1 fetcher yet (Tier B/C, docs/07).
    assert AtsType.JOBVITE not in SUPPORTED_ATS_TYPES
    with pytest.raises(ValueError, match="no Layer-1 fetcher"):
        get_fetcher(AtsType.JOBVITE)
