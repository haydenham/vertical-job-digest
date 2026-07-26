"""HTML → readable plain text for the stored posting description (D-095 PR 2).

Fetchers hand us a description in whatever shape the ATS emits: Greenhouse/Workable/Workday
return HTML, Lever/Ashby prefer a plain-text variant, Radancy/Paylocity already ran the page
through BeautifulSoup. `postings.description` stores **one** normalized plain-text form of that,
so the dashboard can render it without an HTML sanitizer and without a client-side parser.

Two rules this module exists to hold:

- **Block structure survives, inline structure does not.** Job descriptions are mostly bullet
  lists and short headed sections; collapsing them into one space-separated blob (the
  `get_text(" ", strip=True)` shape the Radancy/Paylocity fetchers use for hashing) makes an
  unreadable wall. So paragraphs/list items/headings become their own lines while inline markup
  (`<b>Python</b>` mid-sentence) stays on the line it belongs to, and the panel renders the
  result with `white-space: pre-wrap`.
- **This never touches `content_hash`.** `vja.hashing.content_hash` keys on the fetcher's *raw*
  description string. Normalizing before hashing would flip the hash of every stored posting at
  once — a corpus-wide false "content changed", mass re-extraction, and exactly the churn D-088
  guards against. Normalization happens only on the way into the display column.
"""

from __future__ import annotations

import re
from html import unescape

from bs4 import BeautifulSoup

#: Tags whose text is markup machinery, never posting content. `get_text()` would otherwise
#: inline a tracking script's source into the description.
_NON_CONTENT_TAGS = ("script", "style", "noscript", "template")

#: Tags that start a new line but stay in the same visual group — chiefly list items, which read
#: badly double-spaced (a 15-bullet requirements list would run 30 lines).
_LINE_TAGS = ("br", "dd", "dt", "li", "td", "th", "tr")

#: Tags that start a new *paragraph* (blank line above). Everything not named in either tuple is
#: inline and stays on the current line, which is what keeps `<b>`/`<a>`/`<span>` from shattering
#: a sentence into one word per line.
_PARAGRAPH_TAGS = (
    "address",
    "article",
    "blockquote",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "ul",
)

_HORIZONTAL_WS = re.compile(r"[ \t\xa0]+")

#: Three or more newlines (i.e. two or more blank lines) → one blank line.
_BLANK_RUN = re.compile(r"\n{3,}")

#: A cheap "does this look like markup at all" probe. Plain-text descriptions (Lever's
#: `descriptionPlain`, Radancy's already-parsed page) skip the parser entirely — running them
#: through BeautifulSoup is wasted work and would eat a literal "<" that is real posting content.
_LOOKS_LIKE_HTML = re.compile(r"<[a-zA-Z/!][^>]*>")

#: Greenhouse's `content` field is **escaped** HTML (`&lt;h3&gt;About…`), so the probe above misses
#: it and the body would be stored with its tags showing. One `html.unescape` puts it back into
#: the shape the parser expects. Only applied when escaped markup is actually present, so a plain
#: description that merely mentions "R&amp;D" is left alone.
_ESCAPED_MARKUP = re.compile(r"&lt;\s*[a-zA-Z/!]")


def html_to_text(value: str | None) -> str | None:
    """Return `value` as readable plain text, or `None` when it holds nothing to show.

    Idempotent: text that is already plain comes back with its line structure intact (only
    horizontal whitespace and blank-line runs are tidied), so calling this on a plain-text ATS
    description changes nothing that matters.
    """
    if value is None:
        return None
    if _LOOKS_LIKE_HTML.search(value):
        text = _strip_markup(value)
    elif _ESCAPED_MARKUP.search(value):
        text = _strip_markup(unescape(value))
    else:
        text = value
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # Per-line: HTML indentation would otherwise survive as leading spaces on every line.
    lines = [_HORIZONTAL_WS.sub(" ", line).strip() for line in normalized.split("\n")]
    return _BLANK_RUN.sub("\n\n", "\n".join(lines)).strip() or None


def _strip_markup(value: str) -> str:
    """Parse `value` as HTML and return its text with block boundaries kept as newlines.

    Each block tag gets an explicit newline text node prepended (one for a line, two for a
    paragraph) and the whole tree is then flattened with a *space* separator, so a break happens
    exactly where the markup meant one and nowhere else. Only leading breaks are inserted — the
    next block's own break closes the previous one, and the caller's blank-run collapse tidies
    whatever nesting produced.
    """
    soup = BeautifulSoup(value, "html.parser")
    for tag in soup(_NON_CONTENT_TAGS):
        tag.decompose()
    for tag in soup.find_all(_LINE_TAGS):
        tag.insert_before("\n")
    for tag in soup.find_all(_PARAGRAPH_TAGS):
        tag.insert_before("\n\n")
    # No separator: real markup already carries its own spacing inside the text nodes
    # ("We use <b>Python</b> and SQL"), so joining with a space would strand punctuation
    # ("data ." for "<a>data</a>.").
    return soup.get_text("")
