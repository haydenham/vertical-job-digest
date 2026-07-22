"""Small manual real-model extraction check for the retained production model (D-020/D-090).

The six representative cases rejected DeepSeek V4 Flash/Pro and remain an advisory comparison tool.
Model output is nondeterministic, so this file is opt-in, metered, and never a merge gate.
"""

import os
from dataclasses import dataclass

import pytest
from dotenv import load_dotenv

from vja.extract import extract_posting
from vja.llm import LiteLLMClient
from vja.models import Level, RemoteType

load_dotenv()

pytestmark = pytest.mark.eval

_EVAL_MODEL = "anthropic/claude-haiku-4-5"


@dataclass(frozen=True)
class _Case:
    name: str
    posting: str
    level: Level
    remote: RemoteType
    location_terms: tuple[str, ...] = ()
    stack_terms: tuple[str, ...] = ()
    work_auth_terms: tuple[str, ...] = ()
    comp_min: int | None = None
    comp_max: int | None = None
    comp_raw_terms: tuple[str, ...] = ()
    posted_at_terms: tuple[str, ...] = ()


_CASES = (
    _Case(
        name="senior_hybrid_no_sponsorship",
        posting="""\
Title: Senior Staff Software Engineer — Grid Dispatch Optimization

Location: Austin, TX (Hybrid)
We are hiring a Senior Staff Software Engineer with 10+ years of experience to build dispatch
optimization and LMP forecasting services. Stack: Python, Go, and AWS. Candidates must already
have US work authorization; we are unable to provide visa sponsorship.
""",
        level=Level.SENIOR,
        remote=RemoteType.HYBRID,
        location_terms=("austin",),
        stack_terms=("python", "go", "aws"),
        work_auth_terms=("authorization",),
    ),
    _Case(
        name="new_grad_remote_annual_salary",
        posting="""\
Title: Entry-Level Data Engineer — New Graduate

This fully remote United States role is designed for December 2025 through May 2026 graduates.
You will use Python, SQL, and Snowflake. The annual base salary is $72,000 - $88,000. Visa
sponsorship is available for qualified candidates.
""",
        level=Level.NEW_GRAD,
        remote=RemoteType.REMOTE,
        location_terms=("united states",),
        stack_terms=("python", "sql", "snowflake"),
        work_auth_terms=("sponsor",),
        comp_min=72_000,
        comp_max=88_000,
        comp_raw_terms=("72,000", "88,000"),
    ),
    _Case(
        name="intern_hourly_not_annualized",
        posting="""\
Title: Software Engineering Intern

Summer internship in our Chicago, IL office. This position is onsite five days per week and pays
$28 per hour. Work with TypeScript and React on internal developer tools.
""",
        level=Level.INTERN,
        remote=RemoteType.ONSITE,
        location_terms=("chicago",),
        stack_terms=("typescript", "react"),
        comp_raw_terms=("28", "hour"),
    ),
    _Case(
        name="mid_level_clearance_requirement",
        posting="""\
Title: Software Engineer II

Arlington, VA. Hybrid schedule with three days in the office. The successful candidate has 3-5
years of experience building Java and Kubernetes services. US citizenship and an active Secret
security clearance are required.
""",
        level=Level.MID,
        remote=RemoteType.HYBRID,
        location_terms=("arlington",),
        stack_terms=("java", "kubernetes"),
        work_auth_terms=("citizen", "secret"),
    ),
    _Case(
        name="sparse_posting_does_not_hallucinate",
        posting="""\
Title: Software Developer

Join our product team to build reliable internal tools. Experience with SQL is helpful.
""",
        level=Level.UNKNOWN,
        remote=RemoteType.UNKNOWN,
        stack_terms=("sql",),
    ),
    _Case(
        name="noisy_html_multilocation_salary_and_date",
        posting="""\
Title: Associate Platform Engineer

<div><strong>Posted July 18, 2026</strong></div><p>This early-career role is for engineers with
1-2 years of experience. Work from Denver, CO or Boulder, CO on a hybrid schedule of three office
days per week.</p><ul><li>Python</li><li>Terraform</li><li>Google Cloud Platform (GCP)</li></ul>
<p>Annual base salary range: $95,000–$115,000.</p><p>Candidates must already be authorized to work
in the United States; we cannot provide sponsorship.</p>
""",
        level=Level.EARLY_CAREER,
        remote=RemoteType.HYBRID,
        location_terms=("colorado", "denver", "boulder"),
        stack_terms=("python", "terraform", "gcp"),
        work_auth_terms=("sponsor",),
        comp_min=95_000,
        comp_max=115_000,
        comp_raw_terms=("95,000", "115,000"),
        posted_at_terms=("2026-07-18",),
    ),
)


def _assert_all_terms(actual: str | None, expected: tuple[str, ...]) -> None:
    if not expected:
        assert actual is None
        return
    assert actual is not None
    lowered = actual.lower()
    assert all(term in lowered for term in expected), actual


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_extract_representative_posting(monkeypatch: pytest.MonkeyPatch, case: _Case) -> None:
    monkeypatch.setenv("VJA_EXTRACT_MODEL", _EVAL_MODEL)
    monkeypatch.delenv("VJA_EXTRACT_EFFORT", raising=False)
    call = extract_posting(LiteLLMClient(), case.posting)
    fields, usage = call.value, call.usage

    assert usage.input > 0
    assert fields.level == case.level
    assert fields.remote == case.remote

    if case.location_terms:
        assert fields.location is not None
        location = fields.location.lower()
        assert any(term in location for term in case.location_terms), fields.location
    else:
        assert fields.location is None

    stack = " ".join(fields.stack).lower()
    assert all(term in stack for term in case.stack_terms), fields.stack
    _assert_all_terms(fields.work_auth, case.work_auth_terms)
    assert fields.comp_min == case.comp_min
    assert fields.comp_max == case.comp_max
    _assert_all_terms(fields.comp_raw, case.comp_raw_terms)
    _assert_all_terms(fields.posted_at, case.posted_at_terms)
