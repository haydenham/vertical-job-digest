"""Opt-in LLM eval for matching (P5.3, D-020) — real Sonnet call.

Excluded from the default run; invoke with ``uv run pytest -m eval``. Skipped unless
`ANTHROPIC_API_KEY` is set. This is the path-filtered merge gate (D-020): a structural check (a
schema-valid `MatchResult` with non-empty fits AND gaps and a score in range — D-007) plus two
behavioral checks graded with tolerance — an obviously-wrong role must return `no`/`maybe`, and an
obviously-aligned role must return `yes`/`strong_yes`. Run when a PR touches the match
prompt/schema; a regression here blocks the merge.
"""

import os

import pytest
from anthropic import Anthropic
from dotenv import load_dotenv

from vja.match import match_posting
from vja.models import Verdict

load_dotenv()

pytestmark = pytest.mark.eval

_RESUME = """\
Early-career software engineer. B.S. Computer Science (2024). Internships building Python data
pipelines and a React dashboard. Coursework in optimization and power systems. Personal project:
a nodal electricity-price (LMP) forecasting model. Authorized to work in the US; no sponsorship
needed. Seeking new-grad / early-career roles in grid and power-market software.
"""
_VOCAB = ("power markets", "dispatch optimization", "LMP / nodal pricing", "DER orchestration")

_GOOD_POSTING = """\
Title: Software Engineer, Grid Markets (New Grad)
Level: new_grad
Location: Austin, TX
Remote: hybrid
Stack: Python, React, AWS
"""

_BAD_POSTING = """\
Title: Senior Principal Petroleum Reservoir Engineer
Level: senior
Location: Aberdeen, United Kingdom
Work authorization note: UK work authorization required; no sponsorship.
Stack: Eclipse reservoir simulation, Fortran
"""


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_match_structural_and_obvious_yes() -> None:
    result, usage = match_posting(Anthropic(), _RESUME, _VOCAB, _GOOD_POSTING)

    # Structural (D-007): valid verdict, score in range, non-empty fits AND gaps.
    assert isinstance(result.verdict, Verdict)
    assert 0 <= result.score <= 100
    assert result.fits and result.gaps
    assert usage.input > 0 or usage.cache_read > 0  # real tokens metered (D-069)

    # Behavioral (obvious yes): an aligned early-career grid-software role.
    assert result.verdict in (Verdict.YES, Verdict.STRONG_YES), result.verdict
    assert result.score >= 60


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_match_says_no_to_obvious_mismatch() -> None:
    result, _ = match_posting(Anthropic(), _RESUME, _VOCAB, _BAD_POSTING)

    # Willingness to say no is a product requirement (D-007): a senior non-software UK role.
    assert result.verdict in (Verdict.NO, Verdict.MAYBE), result.verdict
    assert result.score <= 60
    assert result.gaps  # the negatives must be stated
