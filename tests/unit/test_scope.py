"""Unit tests for the Stage-A scope gate (P5.1, D-023).

Pure title logic: keep iff a role keyword matches AND no exclude keyword matches, whole-word and
case-insensitive. No DB, no network.
"""

import pytest

from vja.scope import ScopeConfig, in_scope

_SCOPE = ScopeConfig(
    role_include=("software", "engineer", "developer", "data", "analyst", "machine learning"),
    exclude=("senior", "sr", "staff", "principal", "lead", "director", "sales", "technician"),
)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Software Engineer", True),
        ("Data Scientist (New Grad)", True),  # "data" role keyword
        ("Machine Learning Engineer", True),  # multi-word role keyword
        ("Backend Developer", True),
        ("Sr. Director, Sales", False),  # multiple excludes
        ("Senior Software Engineer", False),  # role match but excluded by seniority
        ("Wind Turbine Technician", False),  # excluded, no role keyword anyway
        ("Staff Data Engineer", False),  # role match but "staff" excluded
        ("Field Operations Manager", False),  # no role keyword (manager not in include)
        ("Lead Software Developer", False),  # "lead" excluded
        ("", False),
    ],
)
def test_in_scope(title: str, expected: bool) -> None:
    assert in_scope(title, _SCOPE) is expected


def test_none_title_is_out_of_scope() -> None:
    assert in_scope(None, _SCOPE) is False


def test_whole_word_matching() -> None:
    scope = ScopeConfig(role_include=("data", "engineer"), exclude=("sr",))
    assert in_scope("Data Engineer", scope) is True  # whole words match
    # "data" is a whole word, not a substring of "database" → DBA isn't pulled in via "data"
    assert in_scope("Database Administrator", scope) is False
    # exclude "sr" must not trip on the substring inside "disregard"
    assert in_scope("Data role, please disregard the rest", scope) is True


def test_requires_a_role_keyword() -> None:
    # An exclude-free title with no role keyword is still out of scope (balanced gate).
    scope = ScopeConfig(role_include=("engineer",), exclude=())
    assert in_scope("Marketing Coordinator", scope) is False
    assert in_scope("Platform Engineer", scope) is True
