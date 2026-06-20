"""Render `DigestContents` into a sendable email (HTML + plaintext) and an audit JSON blob.

"The diff is the product": the body shows what *changed* — new roles (with verified apply links)
and roles that closed — and nothing else. Each new role now carries its match rationale: a
`[verdict · score]` tag and the one-line `rationale` (P5.4 / D-037). The fuller `fits`/`gaps`
lists are kept out of the body (scannability) but recorded in the audit `contents`. Quarantined
postings (links that failed the D-008 gate) are likewise kept out of the body but recorded so an
all-quarantine night is still traceable.

Nothing here is vertical-specific (CLAUDE rule): the vertical slug is humanized generically for the
subject line, so adding a vertical needs no code change.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from vja.digest.assembly import DigestContents, DigestPosting


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def _humanize(vertical: str) -> str:
    """`grid_power_software` -> `Grid Power Software` (generic, not per-vertical)."""
    return vertical.replace("_", " ").replace("-", " ").title()


def _label(posting: DigestPosting) -> str:
    """`Company — Title (Location)`, gracefully degrading when fields are missing."""
    parts = [posting.company]
    if posting.title:
        parts.append(posting.title)
    head = " — ".join(parts)
    return f"{head} ({posting.location})" if posting.location else head


def _verdict_tag(posting: DigestPosting) -> str:
    """`[verdict · score]` for a matched posting, or `''` when there's no rationale (closures)."""
    if posting.verdict is None:
        return ""
    score = "" if posting.score is None else f" · {posting.score}"
    return f"[{posting.verdict}{score}]"


def render_digest(contents: DigestContents) -> RenderedEmail:
    """Build subject + HTML + plaintext from a digest's contents."""
    name = _humanize(contents.vertical)
    n_new, n_closed = len(contents.new), len(contents.closed)
    subject = f"{name}: {n_new} new, {n_closed} closed"
    return RenderedEmail(
        subject=subject,
        html=_render_html(name, contents),
        text=_render_text(name, contents),
    )


def _render_text(name: str, contents: DigestContents) -> str:
    lines = [name, "=" * len(name), ""]
    lines.append(f"New roles ({len(contents.new)})")
    if contents.new:
        for posting in contents.new:
            tag = _verdict_tag(posting)
            head = f"{_label(posting)} {tag}".rstrip()
            link = f" — {posting.apply_url}" if posting.apply_url else ""
            lines.append(f"  • {head}{link}")
            if posting.rationale:
                lines.append(f"      {posting.rationale}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append(f"Closed roles ({len(contents.closed)})")
    if contents.closed:
        lines.extend(f"  • {_label(posting)}" for posting in contents.closed)
    else:
        lines.append("  (none)")
    lines.append("")
    return "\n".join(lines)


def _render_html(name: str, contents: DigestContents) -> str:
    blocks = [f"<h1>{escape(name)}</h1>"]
    blocks.append(f"<h2>New roles ({len(contents.new)})</h2>")
    blocks.append(_html_list(contents.new, linked=True))
    blocks.append(f"<h2>Closed roles ({len(contents.closed)})</h2>")
    blocks.append(_html_list(contents.closed, linked=False))
    body = "\n".join(blocks)
    return f"<!doctype html><html><body>\n{body}\n</body></html>"


def _html_list(postings: list[DigestPosting], *, linked: bool) -> str:
    if not postings:
        return "<p><em>(none)</em></p>"
    items = []
    for posting in postings:
        label = escape(_label(posting))
        if linked and posting.apply_url:
            href = escape(posting.apply_url, quote=True)
            head = f'<a href="{href}">{label}</a>'
        else:
            head = label
        tag = _verdict_tag(posting)
        if tag:
            head += f" <strong>{escape(tag)}</strong>"
        rationale = f"<br><em>{escape(posting.rationale)}</em>" if posting.rationale else ""
        items.append(f"<li>{head}{rationale}</li>")
    return "<ul>\n" + "\n".join(items) + "\n</ul>"


def _posting_to_dict(posting: DigestPosting) -> dict[str, Any]:
    d: dict[str, Any] = {
        "external_id": posting.external_id,
        "company": posting.company,
        "title": posting.title,
        "location": posting.location,
        "apply_url": posting.apply_url,
        "first_seen_at": posting.first_seen_at.isoformat(),
    }
    # The full rationale lands in the audit record even though fits/gaps aren't in the body (D-037).
    if posting.verdict is not None:
        d |= {
            "verdict": posting.verdict,
            "score": posting.score,
            "rationale": posting.rationale,
            "fits": posting.fits,
            "gaps": posting.gaps,
        }
    return d


def contents_to_dict(contents: DigestContents) -> dict[str, Any]:
    """JSON-safe audit record of what the digest comprised (stored in `digests.contents`)."""
    return {
        "vertical": contents.vertical,
        "since": contents.since.isoformat() if contents.since else None,
        "generated_at": contents.generated_at.isoformat(),
        "new": [_posting_to_dict(p) for p in contents.new],
        "closed": [_posting_to_dict(p) for p in contents.closed],
        "quarantined": [_posting_to_dict(p) for p in contents.quarantined],
    }
