"""Unit tests for digest rendering (P3B2, P5.4 rationale).

No DB, no network: build `DigestContents` in memory and assert the subject counts, that
new/closed roles (and apply links) appear in the body, that the match rationale (verdict/score/
one-liner) renders for new roles while fits/gaps stay out of the body but in the audit dict, that
quarantined postings are kept out of the user-facing body, and that `contents_to_dict` is JSON-safe.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from vja.digest.assembly import DigestContents, DigestPosting
from vja.digest.render import contents_to_dict, render_digest

_NOW = datetime(2026, 6, 17, tzinfo=UTC)


def _posting(
    external_id: str,
    *,
    company: str = "Camus",
    apply_url: str | None = None,
    verdict: str | None = None,
    score: int | None = None,
    rationale: str | None = None,
    fits: list[str] | None = None,
    gaps: list[str] | None = None,
) -> DigestPosting:
    return DigestPosting(
        external_id=external_id,
        company=company,
        title="Software Engineer",
        location="Remote",
        apply_url=apply_url,
        first_seen_at=_NOW,
        verdict=verdict,
        score=score,
        rationale=rationale,
        fits=fits,
        gaps=gaps,
    )


def _matched(external_id: str, **kw: object) -> DigestPosting:
    """A `new` posting carrying a match rationale (the P5.4 shape)."""
    defaults: dict[str, object] = {
        "apply_url": "https://jobs/x",
        "verdict": "strong_yes",
        "score": 88,
        "rationale": "Strong grid-software fit at the right level.",
        "fits": ["ERCOT domain", "Python"],
        "gaps": ["No SCADA experience"],
    }
    defaults.update(kw)
    return _posting(external_id, **defaults)  # type: ignore[arg-type]


def _contents(
    *,
    new: Sequence[DigestPosting] = (),
    closed: Sequence[DigestPosting] = (),
    quarantined: Sequence[DigestPosting] = (),
) -> DigestContents:
    return DigestContents(
        vertical="grid_power_software",
        recipient="hayden@example.com",
        since=None,
        generated_at=_NOW,
        new=list(new),
        closed=list(closed),
        quarantined=list(quarantined),
    )


def _closures(spec: dict[str, int]) -> list[DigestPosting]:
    """Build closed postings from `{company: count}` with unique external_ids."""
    out: list[DigestPosting] = []
    for company, n in spec.items():
        for _ in range(n):
            out.append(_posting(f"c{len(out)}", company=company))
    return out


def test_subject_reports_new_and_closed_counts() -> None:
    rendered = render_digest(_contents(new=[_posting("a")], closed=[_posting("b"), _posting("c")]))
    assert rendered.subject == "Grid Power Software: 1 new, 2 closed"


def test_body_lists_new_roles_with_apply_links() -> None:
    rendered = render_digest(_contents(new=[_matched("a")]))
    assert "https://jobs/x" in rendered.html
    assert 'href="https://jobs/x"' in rendered.html
    assert "https://jobs/x" in rendered.text
    assert "Camus" in rendered.html and "Software Engineer" in rendered.text


def test_new_roles_render_verdict_score_and_rationale() -> None:
    rendered = render_digest(_contents(new=[_matched("a")]))
    # The [verdict · score] tag and the one-line rationale appear in both bodies (D-037).
    assert "strong_yes" in rendered.text and "88" in rendered.text
    assert "Strong grid-software fit at the right level." in rendered.text
    assert "strong_yes" in rendered.html and "88" in rendered.html
    assert "Strong grid-software fit at the right level." in rendered.html


def test_fits_and_gaps_stay_out_of_the_body() -> None:
    rendered = render_digest(_contents(new=[_matched("a")]))
    # fits/gaps are persisted in the audit dict but deliberately not rendered (scannability).
    assert "SCADA" not in rendered.html and "SCADA" not in rendered.text
    assert "ERCOT domain" not in rendered.html


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
        new=[_matched("a")],
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
    # The full rationale (incl. fits/gaps) lands in the audit record (D-037).
    assert restored["new"][0]["verdict"] == "strong_yes"
    assert restored["new"][0]["score"] == 88
    assert restored["new"][0]["fits"] == ["ERCOT domain", "Python"]
    assert restored["new"][0]["gaps"] == ["No SCADA experience"]
    # A closure carries no match fields.
    assert "verdict" not in restored["closed"][0]


def test_many_closures_roll_up_by_company() -> None:
    # > 10 closures: the body summarizes by company instead of one bullet each (D-056).
    rendered = render_digest(_contents(closed=_closures({"Boeing": 6, "Airbus": 4, "Vistra": 2})))
    assert rendered.subject == "Grid Power Software: 0 new, 12 closed"  # true count, not summarized
    for body in (rendered.text, rendered.html):
        assert "12 roles across 3 companies" in body
        assert "Boeing: 6" in body
        assert "Airbus: 4" in body
        assert "Vistra: 2" in body
    # Crucially NOT enumerated per role — the per-role title never appears.
    assert "Software Engineer" not in rendered.text
    assert "Software Engineer" not in rendered.html


def test_closure_rollup_collapses_tail_companies() -> None:
    # 11 single-role companies → top 10 named, the 11th collapsed (singular wording).
    rendered = render_digest(_contents(closed=_closures({f"Co{i}": 1 for i in range(11)})))
    for body in (rendered.text, rendered.html):
        assert "11 roles across 11 companies" in body
        assert "…and 1 more company (1 role)" in body


def test_closure_detail_boundary_at_limit() -> None:
    # Exactly 10 → still enumerated per role; 11 → rollup (singular "1 company").
    r10 = render_digest(_contents(closed=_closures({"Boeing": 10})))
    assert "Software Engineer" in r10.text and "roles across" not in r10.text
    r11 = render_digest(_contents(closed=_closures({"Boeing": 11})))
    assert "11 roles across 1 company" in r11.text and "Boeing: 11" in r11.text


def test_few_closures_stay_detailed() -> None:
    closed = [_posting("a", company="Camus"), _posting("b", company="Boeing")]
    rendered = render_digest(_contents(closed=closed))
    assert "Camus · Software Engineer" in rendered.text
    assert "roles across" not in rendered.text


def test_audit_keeps_all_closures_when_body_summarized() -> None:
    # Summarizing the body must not truncate the audit record (D-037 completeness).
    contents = _contents(closed=_closures({"Boeing": 8, "Airbus": 7}))  # 15 > limit
    rendered = render_digest(contents)
    assert "roles across" in rendered.text  # body is summarized
    assert len(contents_to_dict(contents)["closed"]) == 15  # audit keeps every closure


def test_no_unsubscribe_url_leaves_bodies_footer_free() -> None:
    # D-094: dev (no public base URL) / pre-login seed profiles ship without the footer.
    rendered = render_digest(_contents(new=[_matched("a")]))
    assert "Unsubscribe" not in rendered.html
    assert "Unsubscribe" not in rendered.text
    assert "unsubscribe" not in rendered.html.lower()


def test_unsubscribe_url_renders_escaped_footer_in_both_bodies() -> None:
    url = "https://role-feed.com/unsubscribe?token=t&x=1"
    rendered = render_digest(_contents(new=[_matched("a")]), unsubscribe_url=url)
    assert 'href="https://role-feed.com/unsubscribe?token=t&amp;x=1"' in rendered.html
    assert rendered.html.index("Unsubscribe") < rendered.html.index("</body>")
    assert f"Unsubscribe (pauses this email; your dashboard keeps working): {url}" in rendered.text


def test_digest_copy_carries_no_em_dashes() -> None:
    """Regression pin: the digest is the primary user-facing surface (D-010), and em dashes were
    removed from it deliberately. Covers both the rollup path and the per-role path, plus the
    unsubscribe footer, since each built its own separator."""
    few = render_digest(
        _contents(closed=[_posting("a", company="Camus")]), unsubscribe_url="https://x/u"
    )
    many = render_digest(_contents(closed=_closures({"Boeing": 6, "Airbus": 4, "Vistra": 2})))
    for rendered in (few, many):
        assert "—" not in rendered.text
        assert "—" not in rendered.html
        assert "—" not in rendered.subject
