"""`vja.text.html_to_text` — the HTML → plain-text normalizer behind `postings.description`.

The cases here are driven by what the real ATSs actually emit (D-095): raw HTML from
iCIMS/Lever/Workday, **escaped** HTML from Greenhouse, and already-flattened text from
Radancy/Paylocity. The rule under test throughout: block structure survives, inline markup does
not, and nothing renders when there is nothing to say.
"""

from __future__ import annotations

import pytest

from vja.text import html_to_text


@pytest.mark.parametrize("value", [None, "", "   ", "\n\n", "<p></p>", "<div> </div>"])
def test_nothing_to_show_is_none_not_empty_string(value: str | None) -> None:
    # The column means "no body"; an empty string would render an empty block in the panel.
    assert html_to_text(value) is None


def test_paragraphs_are_separated_by_a_blank_line() -> None:
    assert html_to_text("<p>First para.</p><p>Second para.</p>") == "First para.\n\nSecond para."


def test_list_items_are_one_per_line_without_blank_lines_between() -> None:
    # A 15-bullet requirements list double-spaced reads as twice the page for no gain.
    text = html_to_text("<ul><li>Python, SQL</li><li>2+ years</li><li>Grid domain</li></ul>")
    assert text == "Python, SQL\n2+ years\nGrid domain"


def test_headings_start_their_own_paragraph() -> None:
    text = html_to_text("<h3>About the Position</h3><p>We are hiring.</p>")
    assert text == "About the Position\n\nWe are hiring."


def test_inline_markup_stays_on_one_line_with_its_sentence() -> None:
    # The failure this guards: `get_text("\n")` shatters a sentence into one fragment per tag.
    text = html_to_text("<p>We use <b>Python</b> and <a href='/x'>SQL</a>.</p>")
    assert text == "We use Python and SQL."


def test_br_breaks_a_line_without_starting_a_paragraph() -> None:
    assert html_to_text("<p>Line one<br/>line two</p>") == "Line one\nline two"


def test_script_and_style_content_is_dropped() -> None:
    text = html_to_text("<div><script>var x=1;</script><p>Real body.</p><style>.a{}</style></div>")
    assert text == "Real body."


def test_entities_are_decoded_and_nbsp_collapses_to_a_space() -> None:
    assert html_to_text("<p>Vitol&#xa0;is a leader &amp; more</p>") == "Vitol is a leader & more"


def test_escaped_markup_is_unescaped_before_parsing() -> None:
    # Greenhouse's `content` field ships its HTML escaped; without this the stored body would
    # show its own tags to the user.
    greenhouse = "&lt;h3&gt;About&lt;/h3&gt;\n&lt;p&gt;We&#39;re hiring.&lt;/p&gt;"
    assert html_to_text(greenhouse) == "About\n\nWe're hiring."


def test_plain_text_keeps_its_own_line_structure() -> None:
    # Lever's `descriptionPlain` / Radancy's pre-flattened page must pass through unharmed.
    plain = "About the role\n\n- Python\n- SQL"
    assert html_to_text(plain) == plain


def test_a_literal_angle_bracket_in_plain_text_survives() -> None:
    # No markup present ⇒ the parser never runs, so "<" is content, not a broken tag.
    assert html_to_text("Latency < 50ms required") == "Latency < 50ms required"


def test_indentation_and_blank_line_runs_are_tidied() -> None:
    messy = "  Heading  \n\n\n\n    Body line   \n\t\n"
    assert html_to_text(messy) == "Heading\n\nBody line"


def test_table_cells_do_not_run_together() -> None:
    assert html_to_text("<table><tr><td>Salary</td><td>$120,000</td></tr></table>") == (
        "Salary\n$120,000"
    )


def test_is_idempotent() -> None:
    once = html_to_text("<div><h3>Role</h3><p>Build <b>things</b>.</p><ul><li>Go</li></ul></div>")
    assert once is not None
    assert html_to_text(once) == once
