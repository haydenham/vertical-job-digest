"""Manual Sonnet-vs-Luna matching evaluation (D-090 Block 4).

Run this small, metered suite once per approved model/effort configuration with ``-s``. Each
case prints the complete structured judgment plus latency, tokens, model, and catalog cost before
the assertions run, so Hayden can review the actual user-facing text and scores. Model selection
remains a human decision; this file supplies evidence and hard trust-contract checks.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import pytest
from dotenv import load_dotenv

from vja.llm import LiteLLMClient, StructuredResult
from vja.match import MatchResult, match_posting
from vja.models import Verdict

load_dotenv()

pytestmark = pytest.mark.eval


@dataclass(frozen=True)
class _Profile:
    resume: str
    vocabulary: tuple[str, ...]


@dataclass(frozen=True)
class _Case:
    name: str
    profile: _Profile
    posting: str
    allowed_verdicts: tuple[Verdict, ...]
    score_min: int
    score_max: int


_GRID_PROFILE = _Profile(
    resume="""\
Early-career software engineer. B.S. Computer Science (2024). Internships building Python data
pipelines and a React dashboard. Coursework in optimization and power systems. Personal project:
a nodal electricity-price (LMP) forecasting model. Authorized to work in the US; no sponsorship
needed. Seeking new-grad / early-career roles in grid and power-market software.
""",
    vocabulary=(
        "power markets",
        "dispatch optimization",
        "LMP / nodal pricing",
        "DER orchestration",
    ),
)

_AVIATION_PROFILE = _Profile(
    resume="""\
Early-career software engineer. B.S. Computer Science (2024). Internship building Python and SQL
data pipelines plus a React operations dashboard. Coursework in distributed systems and databases.
Built a flight-delay prediction project using public aviation data. Authorized to work in the US;
no sponsorship needed. Seeking early-career aviation-technology roles.
""",
    vocabulary=("flight operations", "airline operations", "dispatch", "aviation data"),
)

_ROBOTICS_PROFILE = _Profile(
    resume="""\
Early-career software engineer. B.S. Computer Science (2024). Internship building Python and C++
telemetry services. Built a ROS 2 mobile-robot capstone and a React monitoring dashboard. Coursework
in embedded systems, but no professional motion-planning or controls experience. Authorized to work
in the US; no sponsorship needed. Seeking new-grad / early-career robotics-software roles.
""",
    vocabulary=("robotics software", "ROS 2", "motion planning", "robot telemetry"),
)

_CASES = (
    _Case(
        name="grid_clear_yes",
        profile=_GRID_PROFILE,
        posting="""\
Title: Software Engineer, Grid Markets (New Grad)
Level: new_grad
Location: Austin, TX
Remote: hybrid
Stack: Python, React, AWS
""",
        allowed_verdicts=(Verdict.YES, Verdict.STRONG_YES),
        score_min=60,
        score_max=100,
    ),
    _Case(
        name="grid_clear_no_senior_nonsoftware_uk",
        profile=_GRID_PROFILE,
        posting="""\
Title: Senior Principal Petroleum Reservoir Engineer
Level: senior
Location: Aberdeen, United Kingdom
Work authorization note: UK work authorization required; no sponsorship.
Stack: Eclipse reservoir simulation, Fortran
""",
        allowed_verdicts=(Verdict.NO, Verdict.MAYBE),
        score_min=0,
        score_max=60,
    ),
    _Case(
        name="grid_ambiguous_mid_level_domain_fit",
        profile=_GRID_PROFILE,
        posting="""\
Title: Software Engineer II, Power Systems Optimization
Level: mid
Location: Chicago, IL
Remote: hybrid
Stack: Python, optimization, AWS
""",
        allowed_verdicts=(Verdict.NO, Verdict.MAYBE),
        score_min=0,
        score_max=60,
    ),
    _Case(
        name="grid_ambiguous_technical_fit_domain_distance",
        profile=_GRID_PROFILE,
        posting="""\
Title: Junior Full-Stack Software Engineer
Level: early_career
Location: Denver, CO
Remote: onsite
Stack: Python, React, AWS
""",
        allowed_verdicts=(Verdict.MAYBE, Verdict.YES),
        score_min=35,
        score_max=85,
    ),
    _Case(
        name="aviation_clear_yes",
        profile=_AVIATION_PROFILE,
        posting="""\
Title: Associate Software Engineer, Flight Operations
Level: early_career
Location: Dallas, TX
Remote: hybrid
Stack: Python, SQL, React, AWS
""",
        allowed_verdicts=(Verdict.YES, Verdict.STRONG_YES),
        score_min=60,
        score_max=100,
    ),
    _Case(
        name="aviation_clear_no_canada_work_auth",
        profile=_AVIATION_PROFILE,
        posting="""\
Title: Junior Avionics Software Developer
Level: early_career
Location: Montreal, Canada
Remote: onsite
Work authorization note: Canadian citizenship required; no sponsorship.
Stack: C++, embedded systems, DO-178C
""",
        allowed_verdicts=(Verdict.NO, Verdict.MAYBE),
        score_min=0,
        score_max=60,
    ),
    _Case(
        name="robotics_clear_yes",
        profile=_ROBOTICS_PROFILE,
        posting="""\
Title: New Graduate Robotics Software Engineer
Level: new_grad
Location: Pittsburgh, PA
Remote: onsite
Stack: C++, Python, ROS 2
""",
        allowed_verdicts=(Verdict.YES, Verdict.STRONG_YES),
        score_min=60,
        score_max=100,
    ),
    _Case(
        name="robotics_ambiguous_seniority_gap",
        profile=_ROBOTICS_PROFILE,
        posting="""\
Title: Robotics Software Engineer, Motion Planning
Level: mid
Location: San Francisco, CA
Remote: onsite
Stack: C++, ROS 2, motion planning, controls
""",
        allowed_verdicts=(Verdict.NO, Verdict.MAYBE),
        score_min=0,
        score_max=60,
    ),
)


def _provider_key_name(model: str) -> str:
    if model.startswith("anthropic/"):
        return "ANTHROPIC_API_KEY"
    if model.startswith("openai/"):
        return "OPENAI_API_KEY"
    raise ValueError(f"matching eval has no approved credential mapping for {model!r}")


def _assert_verdict_score_consistent(result: MatchResult) -> None:
    bands = {
        Verdict.NO: (0, 35),
        Verdict.MAYBE: (35, 60),
        Verdict.YES: (60, 85),
        Verdict.STRONG_YES: (85, 100),
    }
    lower, upper = bands[result.verdict]
    assert lower <= result.score <= upper, (
        f"{result.verdict.value} verdict is inconsistent with score {result.score}"
    )


def _print_review_record(case: _Case, call: StructuredResult[MatchResult]) -> None:
    record = {
        "case": case.name,
        "requested_model": os.environ.get("VJA_MATCH_MODEL", "openai/gpt-5.6-luna"),
        "actual_model": call.model,
        "effort": os.environ.get("VJA_MATCH_EFFORT", "low"),
        "verdict": call.value.verdict.value,
        "score": call.value.score,
        "fits": call.value.fits,
        "gaps": call.value.gaps,
        "rationale": call.value.rationale,
        "latency_seconds": round(call.latency_seconds, 3),
        "tokens": {
            "input": call.usage.input,
            "output": call.usage.output,
            "cache_read": call.usage.cache_read,
            "cache_write": call.usage.cache_write,
        },
        "catalog_cost_usd": call.cost_usd,
    }
    print("\nMATCH_EVAL " + json.dumps(record, ensure_ascii=False, sort_keys=True))


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_match_representative_case(case: _Case) -> None:
    model = os.environ.get("VJA_MATCH_MODEL", "openai/gpt-5.6-luna")
    key_name = _provider_key_name(model)
    if not os.environ.get(key_name):
        pytest.skip(f"needs {key_name}")

    call = match_posting(
        LiteLLMClient(),
        case.profile.resume,
        case.profile.vocabulary,
        case.posting,
    )
    result = call.value
    _print_review_record(case, call)

    assert result.fits, "fits must be non-empty (D-007)"
    assert result.gaps, "gaps must be non-empty (D-007)"
    assert result.rationale.strip(), "rationale must be non-empty (D-007)"
    assert call.usage.input > 0 or call.usage.cache_read > 0
    _assert_verdict_score_consistent(result)
    assert result.verdict in case.allowed_verdicts, result.verdict
    assert case.score_min <= result.score <= case.score_max, result.score
