"""Unit tests for digest rendering (P3B2).

No DB, no network: build `DigestContents` in memory and assert the subject counts, that
new/closed roles (and apply links) appear in the body, that quarantined postings are kept
out of the user-facing body, and that `contents_to_dict` is JSON-safe.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from vja.digest.assembly import DigestContents, DigestPosting
from vja.digest.render import contents_to_dict, render_digest

_NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _posting(
    external_id: str, *, company: str = "Camus", apply_url: str | None = None
) -> DigestPosting:
    return DigestPosting(
        external_id=external_id,
        company=company,
        title="Software Engineer",
        location="Remote",
        apply_url=apply_url,
        first_seen_at=_NOW,
    )


def _contents(
    *,
    new: Sequence[DigestPosting] = (),
    closed: Sequence[DigestPosting] = (),
    quarantined: Sequence[DigestPosting] = (),
) -> DigestContents:
    return DigestContents(
        vertical="grid_power_software",
        since=None,
        generated_at=_NOW,
        new=list(new),
        closed=list(closed),
        quarantined=list(quarantined),
    )


def test_subject_reports_new_and_closed_counts() -> None:
    rendered = render_digest(_contents(new=[_posting("a")], closed=[_posting("b"), _posting("c")]))
    assert rendered.subject == "Grid Power Software: 1 new, 2 closed"


def test_body_lists_new_roles_with_apply_links() -> None:
    rendered = render_digest(_contents(new=[_posting("a", apply_url="https://jobs/x")]))
    assert "https://jobs/x" in rendered.html
    assert 'href="https://jobs/x"' in rendered.html
    assert "https://jobs/x" in rendered.text
    assert "Camus" in rendered.html and "Software Engineer" in rendered.text


def test_closed_roles_appear_without_links() -> None:
    rendered = render_digest(_contents(closed=[_posting("gone", apply_url="https://stale/1")]))
    assert "Closed roles (1)" in rendered.html
    # A closed role is informational only — no apply link rendered for it.
    assert 'href="https://stale/1"' not in rendered.html


def test_quarantined_postings_are_not_in_the_body() -> None:
    dead = _posting("dead", company="SecretCo", apply_url="https://dead/9")
    rendered = render_digest(_contents(new=[_posting("good")], quarantined=[dead]))
    assert "SecretCo" not in rendered.html
    assert "SecretCo" not in rendered.text
    assert "https://dead/9" not in rendered.html


def test_empty_sections_render_none_placeholder() -> None:
    rendered = render_digest(_contents())
    assert "New roles (0)" in rendered.html
    assert "(none)" in rendered.text


def test_contents_to_dict_is_json_safe_and_complete() -> None:
    contents = _contents(
        new=[_posting("a", apply_url="https://jobs/x")],
        closed=[_posting("b")],
        quarantined=[_posting("dead")],
    )
    blob = contents_to_dict(contents)
    # Round-trips through JSON (the column is sa.JSON) — datetimes are isoformat strings.
    restored = json.loads(json.dumps(blob))
    assert restored["vertical"] == "grid_power_software"
    assert restored["since"] is None
    assert restored["generated_at"] == _NOW.isoformat()
    assert [p["external_id"] for p in restored["new"]] == ["a"]
    assert [p["external_id"] for p in restored["quarantined"]] == ["dead"]
    assert restored["new"][0]["first_seen_at"] == _NOW.isoformat()
