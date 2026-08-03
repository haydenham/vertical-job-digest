"""Render `DigestContents` into a sendable email (HTML + plaintext) and an audit JSON blob.

"The diff is the product": the body shows what *changed* — new roles (with verified apply links)
and roles that closed (rolled up by company once there are many — D-056) — and nothing else.
Each new role now carries its match rationale: a
`[verdict · score]` tag and the one-line `rationale` (P5.4 / D-037). The fuller `fits`/`gaps`
lists are kept out of the body (scannability) but recorded in the audit `contents`. Quarantined
postings (links that failed the D-008 gate) are likewise kept out of the body but recorded so an
all-quarantine night is still traceable. Above all of it sits the one link back into the product
(D-102) — the apply links leave for the employer's ATS, so without it the email is a dead end.

Nothing here is vertical-specific (CLAUDE rule): the vertical slug is humanized generically for the
subject line, so adding a vertical needs no code change.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape
from typing import Any

from vja.digest.assembly import DigestContents, DigestPosting
from vja.location import us_location_display

# Above this many closures the body rolls them up by company instead of one bullet each — a
# backlog day would otherwise bury the new roles under hundreds of dead-link lines (D-056).
_CLOSED_DETAIL_LIMIT = 10
# How many companies to name in the rollup before collapsing the rest into an "…and more" line.
_ROLLUP_TOP_COMPANIES = 10
# The one way back into the product from the email (D-102). Copy is shared by both bodies so
# the HTML anchor text and the plaintext label can't drift apart.
_DASHBOARD_LABEL = "Open your Rolefeed dashboard"


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def _humanize(vertical: str) -> str:
    """`grid_power_software` -> `Grid Power Software` (generic, not per-vertical)."""
    return vertical.replace("_", " ").replace("-", " ").title()


def _label(posting: DigestPosting) -> str:
    """`Company · Title (Location)`, gracefully degrading when fields are missing.

    The location is normalized for reading (D-106); the raw ATS string is what `_posting_to_dict`
    records in the audit blob, so the email and the audit trail differ on purpose.
    """
    parts = [posting.company]
    if posting.title:
        parts.append(posting.title)
    head = " · ".join(parts)
    location = us_location_display(posting.location) or posting.location
    return f"{head} ({location})" if location else head


def _verdict_tag(posting: DigestPosting) -> str:
    """`[verdict · score]` for a matched posting, or `''` when there's no rationale (closures)."""
    if posting.verdict is None:
        return ""
    score = "" if posting.score is None else f" · {posting.score}"
    return f"[{posting.verdict}{score}]"


def _plural(n: int, word: str) -> str:
    """Naive pluralizer for the two words we need: `company`/`companies`, `role`/`roles`."""
    if n == 1:
        return word
    return f"{word[:-1]}ies" if word.endswith("y") else f"{word}s"


def _rollup_split(
    closed: list[DigestPosting],
) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """Closures ranked by company (count desc) → (named top companies, collapsed tail)."""
    ranked = Counter(p.company for p in closed).most_common()
    return ranked[:_ROLLUP_TOP_COMPANIES], ranked[_ROLLUP_TOP_COMPANIES:]


def dashboard_url(base_url: str) -> str:
    """The absolute dashboard link: `{base}/dashboard` (D-102).

    `/dashboard` rather than `/`: a logged-out click bounces through `/login` and lands back on
    the dashboard, whereas `/` would show a returning reader the marketing landing page.
    """
    return f"{base_url.rstrip('/')}/dashboard"


def render_digest(
    contents: DigestContents,
    *,
    unsubscribe_url: str | None = None,
    dashboard_url: str | None = None,
) -> RenderedEmail:
    """Build subject + HTML + plaintext from a digest's contents.

    `unsubscribe_url` (D-094) adds the no-login unsubscribe footer; None (dev without a public
    base URL, or a pre-login seed profile with no `users` row) leaves the output unchanged.
    `dashboard_url` (D-102) adds the link back into the product, directly under the heading;
    None (dev without a public base URL) likewise leaves the output unchanged — never a
    localhost link in an email.
    """
    name = _humanize(contents.vertical)
    n_new, n_closed = len(contents.new), len(contents.closed)
    subject = f"{name}: {n_new} new, {n_closed} closed"
    return RenderedEmail(
        subject=subject,
        html=_render_html(
            name, contents, unsubscribe_url=unsubscribe_url, dashboard_url=dashboard_url
        ),
        text=_render_text(
            name, contents, unsubscribe_url=unsubscribe_url, dashboard_url=dashboard_url
        ),
    )


def _render_text(
    name: str,
    contents: DigestContents,
    *,
    unsubscribe_url: str | None,
    dashboard_url: str | None,
) -> str:
    lines = [name, "=" * len(name), ""]
    if dashboard_url:
        lines.append(f"{_DASHBOARD_LABEL}: {dashboard_url}")
        lines.append("")
    lines.append(f"New roles ({len(contents.new)})")
    if contents.new:
        for posting in contents.new:
            tag = _verdict_tag(posting)
            head = f"{_label(posting)} {tag}".rstrip()
            link = f" · {posting.apply_url}" if posting.apply_url else ""
            lines.append(f"  • {head}{link}")
            if posting.rationale:
                lines.append(f"      {posting.rationale}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append(f"Closed roles ({len(contents.closed)})")
    if not contents.closed:
        lines.append("  (none)")
    elif len(contents.closed) <= _CLOSED_DETAIL_LIMIT:
        lines.extend(f"  • {_label(posting)}" for posting in contents.closed)
    else:
        top, tail = _rollup_split(contents.closed)
        companies = len(top) + len(tail)
        lines.append(
            f"  {len(contents.closed)} roles across {companies} {_plural(companies, 'company')}:"
        )
        lines.extend(f"    • {company}: {n}" for company, n in top)
        if tail:
            tail_roles = sum(n for _, n in tail)
            lines.append(
                f"    …and {len(tail)} more {_plural(len(tail), 'company')} "
                f"({tail_roles} {_plural(tail_roles, 'role')})"
            )
    lines.append("")
    if unsubscribe_url:
        lines.append(
            f"Unsubscribe (pauses this email; your dashboard keeps working): {unsubscribe_url}"
        )
        lines.append("")
    return "\n".join(lines)


def _render_html(
    name: str,
    contents: DigestContents,
    *,
    unsubscribe_url: str | None,
    dashboard_url: str | None,
) -> str:
    blocks = [f"<h1>{escape(name)}</h1>"]
    if dashboard_url:
        href = escape(dashboard_url, quote=True)
        blocks.append(f'<p><a href="{href}">{_DASHBOARD_LABEL}</a></p>')
    blocks.append(f"<h2>New roles ({len(contents.new)})</h2>")
    blocks.append(_html_list(contents.new, linked=True))
    blocks.append(f"<h2>Closed roles ({len(contents.closed)})</h2>")
    blocks.append(_closed_html(contents.closed))
    if unsubscribe_url:
        href = escape(unsubscribe_url, quote=True)
        blocks.append(
            '<hr><p style="color:#888;font-size:12px">You get this digest because you signed up '
            f'for Rolefeed. <a href="{href}">Unsubscribe</a>. Matching and your dashboard keep '
            "working.</p>"
        )
    body = "\n".join(blocks)
    return f"<!doctype html><html><body>\n{body}\n</body></html>"


def _closed_html(closed: list[DigestPosting]) -> str:
    """Closed-roles HTML: a per-role list when few, a per-company rollup when many (D-056)."""
    if len(closed) <= _CLOSED_DETAIL_LIMIT:
        return _html_list(closed, linked=False)
    top, tail = _rollup_split(closed)
    companies = len(top) + len(tail)
    items = [f"<li>{escape(company)}: {n}</li>" for company, n in top]
    if tail:
        tail_roles = sum(n for _, n in tail)
        items.append(
            f"<li>…and {len(tail)} more {_plural(len(tail), 'company')} "
            f"({tail_roles} {_plural(tail_roles, 'role')})</li>"
        )
    summary = f"<p>{len(closed)} roles across {companies} {_plural(companies, 'company')}:</p>"
    return summary + "<ul>\n" + "\n".join(items) + "\n</ul>"


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
