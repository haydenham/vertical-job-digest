"""Unit tests for the in-app feedback email (D-100).

The report is written by a user and read in a mail client, so the escaping test is the one that
matters: everything interpolated into the HTML body is untrusted text.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from vja.digest.feedback import (
    FEEDBACK_MAX_CHARS,
    FeedbackCategory,
    FeedbackReport,
    render_feedback,
    send_feedback,
)
from vja.digest.render import RenderedEmail
from vja.digest.send import DigestConfig

_NOW = datetime(2026, 7, 27, 9, 30, tzinfo=UTC)
_CONFIG = DigestConfig(api_key="k", sender="digest@role-feed.com", recipient="ops@example.com")


def _report(**overrides: Any) -> FeedbackReport:
    defaults: dict[str, Any] = {
        "category": FeedbackCategory.BUG,
        "message": "The apply link on the top row 404s.",
        "user_email": "beta@example.com",
        "user_name": "Beta User",
        "vertical": "grid_power_software",
        "page": "/dashboard",
        "user_agent": "Mozilla/5.0 (Macintosh)",
        "submitted_at": _NOW,
    }
    return FeedbackReport(**(defaults | overrides))


def test_subject_names_the_category_and_sender() -> None:
    rendered = render_feedback(_report())
    assert rendered.subject == "Rolefeed feedback (bug) from beta@example.com"


def test_text_body_carries_every_field() -> None:
    text = render_feedback(_report()).text
    assert "The apply link on the top row 404s." in text
    assert "Beta User <beta@example.com>" in text
    assert "grid_power_software" in text
    assert "/dashboard" in text
    assert "Mozilla/5.0 (Macintosh)" in text
    assert _NOW.isoformat() in text
    assert "Bug" in text


def test_html_escapes_everything_the_user_supplied() -> None:
    """A report is untrusted text landing in a mail client: it must never render as markup."""
    html = render_feedback(
        _report(
            message="<script>alert(1)</script> & <b>bold</b>",
            user_name="<img src=x onerror=alert(1)>",
            page="/dashboard?q=<script>",
            user_agent="<iframe>",
        )
    ).html
    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "<iframe>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&amp;" in html


def test_html_preserves_the_users_line_breaks_without_markup() -> None:
    html = render_feedback(_report(message="line one\nline two")).html
    assert "white-space:pre-wrap" in html
    assert "line one\nline two" in html


def test_missing_context_degrades_to_explicit_placeholders() -> None:
    """A signed-in user with no profile is exactly who reports onboarding bugs, so the email says
    so rather than rendering an empty cell."""
    rendered = render_feedback(_report(vertical=None, page=None, user_agent=None, user_name=None))
    assert "(not onboarded)" in rendered.text
    assert "(unknown)" in rendered.text
    # No name ⇒ the bare address, not a dangling "None <…>".
    assert "beta@example.com" in rendered.text
    assert "None" not in rendered.text


def test_long_user_agent_is_truncated() -> None:
    text = render_feedback(_report(user_agent="U" * 900)).text
    assert "U" * 300 in text
    assert "U" * 301 not in text


def test_a_max_length_message_renders_whole() -> None:
    message = "x" * FEEDBACK_MAX_CHARS
    assert message in render_feedback(_report(message=message)).text


def test_send_feedback_goes_to_the_ops_recipient_with_a_reply_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ops recipient is `send_email`'s default (D-037), and Reply-To points at the user so a
    reply reaches whoever wrote the report."""
    captured: dict[str, Any] = {}

    def fake_send(
        config: DigestConfig,
        rendered: RenderedEmail,
        *,
        recipient: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        captured.update(config=config, rendered=rendered, recipient=recipient, headers=headers)

    monkeypatch.setattr("vja.digest.feedback.send_email", fake_send)
    send_feedback(_CONFIG, _report())

    assert captured["recipient"] is None  # ⇒ send_email's default, the ops address
    assert captured["headers"] == {"Reply-To": "beta@example.com"}
    assert captured["rendered"].subject.endswith("from beta@example.com")
