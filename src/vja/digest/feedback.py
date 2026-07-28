"""Render + send an in-app feedback report as an email to the operator (D-100).

Beta users report bugs and rough edges from a dialog in the SPA; each submission becomes one
transactional email to the ops/alert recipient (`VJA_DIGEST_RECIPIENT` — the same address the
nightly failure alert uses, D-037). **Nothing is persisted**: there is no `feedback` table, so
this path needs no migration and stays outside the `DELETE /api/me` deletion promise (D-094).

Lives inside `vja.digest` on purpose. It is an outbound transactional email, so it reuses
`render.RenderedEmail` and `send.send_email` directly — a sibling top-level module could not,
since the import-linter layers contract treats same-layer packages as independent.

Everything the user typed is untrusted text on its way into a mail client, so the HTML body
escapes every interpolated value (the `render.py` convention).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from html import escape

from vja.digest.render import RenderedEmail
from vja.digest.send import DigestConfig, send_email

# The only abuse guard on the write path besides `require_user` (D-100). An invite-only beta
# behind Google OAuth does not need a per-user throttle, which would cost a `users` column and
# therefore a manual Neon migration (D-083).
FEEDBACK_MAX_CHARS = 5000

# How much of a browser UA string is worth carrying. Long enough to identify the browser and OS,
# short enough that it cannot pad the email.
_MAX_USER_AGENT_CHARS = 300


class FeedbackCategory(StrEnum):
    """What kind of report this is. Mirrored one-to-one by the SPA's `FeedbackCategory` union."""

    BUG = "bug"
    IDEA = "idea"
    CONFUSING = "confusing"
    OTHER = "other"


# Display labels for the email; the wire values stay the lowercase enum members.
_CATEGORY_LABELS = {
    FeedbackCategory.BUG: "Bug",
    FeedbackCategory.IDEA: "Idea",
    FeedbackCategory.CONFUSING: "Confusing",
    FeedbackCategory.OTHER: "Other",
}

_NOT_ONBOARDED = "(not onboarded)"
_UNKNOWN = "(unknown)"


@dataclass(frozen=True)
class FeedbackReport:
    """One submission. Everything except `category`/`message`/`page` is resolved server-side."""

    category: FeedbackCategory
    message: str
    user_email: str
    user_name: str | None
    vertical: str | None
    page: str | None
    user_agent: str | None
    submitted_at: datetime


def _fields(report: FeedbackReport) -> list[tuple[str, str]]:
    """The report's metadata as ordered (label, value) pairs, shared by both body renderers."""
    sender = f"{report.user_name} <{report.user_email}>" if report.user_name else report.user_email
    agent = (report.user_agent or _UNKNOWN)[:_MAX_USER_AGENT_CHARS]
    return [
        ("Category", _CATEGORY_LABELS[report.category]),
        ("From", sender),
        ("Vertical", report.vertical or _NOT_ONBOARDED),
        ("Page", report.page or _UNKNOWN),
        ("Submitted", report.submitted_at.isoformat()),
        ("Browser", agent),
    ]


def render_feedback(report: FeedbackReport) -> RenderedEmail:
    """Build the operator email: who said it, where they were, and what they wrote."""
    subject = f"Rolefeed feedback ({report.category.value}) from {report.user_email}"
    return RenderedEmail(
        subject=subject,
        html=_render_html(report),
        text=_render_text(report),
    )


def _render_text(report: FeedbackReport) -> str:
    heading = "Rolefeed feedback"
    lines = [heading, "=" * len(heading), ""]
    width = max(len(label) for label, _ in _fields(report)) + 2
    lines.extend(f"{label + ':':<{width}}{value}" for label, value in _fields(report))
    lines.extend(["", "Message", "-------", report.message, ""])
    return "\n".join(lines)


def _render_html(report: FeedbackReport) -> str:
    rows = "\n".join(
        f"<tr><td><strong>{escape(label)}</strong></td><td>{escape(value)}</td></tr>"
        for label, value in _fields(report)
    )
    # `white-space: pre-wrap` keeps the user's own line breaks without turning the body into HTML.
    body = (
        "<h1>Rolefeed feedback</h1>\n"
        f"<table>\n{rows}\n</table>\n"
        "<h2>Message</h2>\n"
        f'<p style="white-space:pre-wrap">{escape(report.message)}</p>'
    )
    return f"<!doctype html><html><body>\n{body}\n</body></html>"


def send_feedback(config: DigestConfig, report: FeedbackReport) -> None:
    """Email one report to the ops recipient. Raises `SendError` if Resend rejects it.

    `Reply-To` points at the user so a reply lands with the person who wrote it. Resend's
    canonical field is a top-level `reply_to`, so treat the header as best-effort: the address is
    in the body regardless, and nothing is lost if the provider ignores it.
    """
    send_email(
        config,
        render_feedback(report),
        headers={"Reply-To": report.user_email},
    )
