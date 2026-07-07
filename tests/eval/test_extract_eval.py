"""Opt-in LLM eval for extraction (P5.2, D-020) — real Haiku call.

Excluded from the default run; invoke with ``uv run pytest -m eval``. Skipped unless
`ANTHROPIC_API_KEY` is set. This is the path-filtered merge gate (D-020): a structural check (the
model returns a schema-valid `ExtractedFields`) plus an obvious-case behavioral check graded with
tolerance — a clearly-senior US role with a named stack should extract correctly. Run when a PR
touches the extraction prompt/schema; a regression here blocks the merge.
"""

import os

import pytest
from anthropic import Anthropic
from dotenv import load_dotenv

from vja.extract import extract_posting
from vja.models import Level, RemoteType

load_dotenv()

pytestmark = pytest.mark.eval

_POSTING = """\
Title: Senior Staff Software Engineer — Grid Dispatch Optimization

Location: Austin, TX (Hybrid)
About the role: We are hiring a Senior Staff Software Engineer with 10+ years of experience to
build dispatch-optimization and LMP forecasting services. Stack: Python, Go, and AWS. This role
requires US work authorization; we are unable to provide visa sponsorship.
"""


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_extract_obvious_senior_us_role() -> None:
    fields, usage = extract_posting(Anthropic(), _POSTING)

    # Structural: a schema-valid result with real metered tokens (D-069).
    assert isinstance(fields.level, Level)
    assert isinstance(fields.remote, RemoteType)
    assert usage.input > 0

    # Behavioral (obvious case): the posting is explicit on each of these.
    assert fields.level == Level.SENIOR
    assert fields.remote == RemoteType.HYBRID
    stack_lower = {s.lower() for s in fields.stack}
    assert {"python", "go", "aws"} & stack_lower, fields.stack
    assert fields.work_auth is not None  # sponsorship/citizenship was stated
