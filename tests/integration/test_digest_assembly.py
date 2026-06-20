"""Integration tests for digest assembly + the verification gate (P3B1, P5.4 rationale).

Real migrated SQLite; employers/postings/profiles/matches/digests seeded directly; verification
faked (a `Callable[[str], bool]`) so no network. Pins the window logic, the baseline rule, vertical
isolation, dead-link quarantine, and the P5.4 match-gating: a `new` posting appears only if it has
a relevant match (verdict maybe/yes/strong_yes) for *this* profile, ordered by score descending.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine

from vja.db.engine import begin
from vja.db.matches import save_match
from vja.db.profiles import Profile, active_profiles, upsert_profile
from vja.db.schema import digests, employers, postings
from vja.digest.assembly import build_digest, last_sent_at

_PASS = lambda _url: True  # noqa: E731  (tiny test stub; a def would be noisier)
_EMAIL = "me@example.com"


def _employer(engine: Engine, *, vertical: str = "grid_power_software", name: str = "Co") -> int:
    now = datetime.now(UTC)
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical=vertical,
                name=name,
                ats_type="greenhouse",
                ats_slug=name.lower(),
                source="manual",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _posting(
    engine: Engine,
    employer_id: int,
    external_id: str,
    *,
    first_seen: datetime,
    status: str = "open",
    closed_at: datetime | None = None,
    apply_url: str = "https://jobs.example.com/x",
) -> int:
    with begin(engine) as conn:
        result = conn.execute(
            postings.insert().values(
                employer_id=employer_id,
                external_id=external_id,
                content_hash=f"h-{external_id}",
                raw_payload={},
                apply_url=apply_url,
                title="Engineer",
                location="Remote",
                status=status,
                first_seen_at=first_seen,
                last_seen_at=first_seen,
                closed_at=closed_at,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _profile(
    engine: Engine, *, vertical: str = "grid_power_software", email: str = _EMAIL
) -> Profile:
    upsert_profile(
        engine, user_email=email, vertical=vertical, resume_text="resume", domain_vocabulary=[]
    )
    return next(p for p in active_profiles(engine, vertical) if p.user_email == email)


def _match(
    engine: Engine,
    posting_id: int,
    profile: Profile,
    *,
    verdict: str = "yes",
    score: int = 70,
) -> None:
    with begin(engine) as conn:
        save_match(
            conn,
            posting_id,
            profile.id,
            profile.resume_version,
            {"verdict": verdict, "score": score, "fits": "[]", "gaps": "[]", "rationale": "ok"},
            model="claude-sonnet-4-6",
            trigger="nightly",
            now=datetime.now(UTC),
        )


def _digest(
    engine: Engine,
    *,
    vertical: str,
    status: str,
    sent_at: datetime | None,
    recipient: str = _EMAIL,
) -> None:
    with begin(engine) as conn:
        conn.execute(
            digests.insert().values(
                recipient=recipient,
                vertical=vertical,
                status=status,
                sent_at=sent_at,
                contents={},
            )
        )


def test_baseline_first_digest_is_all_relevant_open(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    now = datetime(2026, 6, 16, tzinfo=UTC)
    a = _posting(migrated_engine, emp, "a", first_seen=now)
    b = _posting(migrated_engine, emp, "b", first_seen=now)
    _posting(migrated_engine, emp, "old", first_seen=now, status="closed", closed_at=now)
    _match(migrated_engine, a, prof)
    _match(migrated_engine, b, prof)

    contents = build_digest(migrated_engine, "grid_power_software", profile=prof, verify=_PASS)

    assert contents.since is None
    assert {p.external_id for p in contents.new} == {"a", "b"}  # the matched open ones
    assert contents.closed == []  # no prior state on the first digest
    assert contents.quarantined == []


def test_unmatched_and_no_verdict_postings_drop_out(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    now = datetime(2026, 6, 16, tzinfo=UTC)
    matched = _posting(migrated_engine, emp, "matched", first_seen=now)
    rejected = _posting(migrated_engine, emp, "rejected", first_seen=now)
    _posting(
        migrated_engine, emp, "unmatched", first_seen=now
    )  # extracted-but-no-match / out-of-scope
    _match(migrated_engine, matched, prof, verdict="yes", score=70)
    _match(migrated_engine, rejected, prof, verdict="no", score=10)

    contents = build_digest(migrated_engine, "grid_power_software", profile=prof, verify=_PASS)

    # Only the relevant match shows: `no` and unmatched postings are not inbox-worthy (D-037).
    assert {p.external_id for p in contents.new} == {"matched"}


def test_new_roles_sorted_by_score_desc(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    now = datetime(2026, 6, 16, tzinfo=UTC)
    low = _posting(migrated_engine, emp, "low", first_seen=now)
    high = _posting(migrated_engine, emp, "high", first_seen=now)
    mid = _posting(migrated_engine, emp, "mid", first_seen=now)
    _match(migrated_engine, low, prof, verdict="maybe", score=40)
    _match(migrated_engine, high, prof, verdict="strong_yes", score=95)
    _match(migrated_engine, mid, prof, verdict="yes", score=70)

    contents = build_digest(migrated_engine, "grid_power_software", profile=prof, verify=_PASS)

    assert [p.external_id for p in contents.new] == ["high", "mid", "low"]
    assert [p.verdict for p in contents.new] == ["strong_yes", "yes", "maybe"]


def test_window_includes_only_changes_after_since(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    cutoff = datetime(2026, 6, 16, tzinfo=UTC)
    before = cutoff - timedelta(days=1)
    after = cutoff + timedelta(days=1)
    old_open = _posting(migrated_engine, emp, "old-open", first_seen=before)
    new_open = _posting(migrated_engine, emp, "new-open", first_seen=after)
    _posting(
        migrated_engine, emp, "old-closed", first_seen=before, status="closed", closed_at=before
    )
    _posting(
        migrated_engine, emp, "new-closed", first_seen=before, status="closed", closed_at=after
    )
    _match(migrated_engine, old_open, prof)
    _match(migrated_engine, new_open, prof)

    contents = build_digest(
        migrated_engine, "grid_power_software", profile=prof, since=cutoff, verify=_PASS
    )

    assert {p.external_id for p in contents.new} == {"new-open"}
    assert {p.external_id for p in contents.closed} == {"new-closed"}


def test_since_auto_resolves_from_last_sent_digest(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    cutoff = datetime(2026, 6, 16, tzinfo=UTC)
    _digest(migrated_engine, vertical="grid_power_software", status="sent", sent_at=cutoff)
    old = _posting(migrated_engine, emp, "old", first_seen=cutoff - timedelta(days=1))
    fresh = _posting(migrated_engine, emp, "fresh", first_seen=cutoff + timedelta(days=1))
    _match(migrated_engine, old, prof)
    _match(migrated_engine, fresh, prof)

    contents = build_digest(migrated_engine, "grid_power_software", profile=prof, verify=_PASS)

    assert contents.since == cutoff
    assert {p.external_id for p in contents.new} == {"fresh"}


def test_dead_links_are_quarantined(migrated_engine: Engine) -> None:
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    now = datetime(2026, 6, 16, tzinfo=UTC)
    good = _posting(migrated_engine, emp, "good", first_seen=now, apply_url="https://ok/1")
    dead = _posting(migrated_engine, emp, "dead", first_seen=now, apply_url="https://dead/2")
    _match(migrated_engine, good, prof)
    _match(migrated_engine, dead, prof)

    contents = build_digest(
        migrated_engine,
        "grid_power_software",
        profile=prof,
        verify=lambda url: url != "https://dead/2",
    )

    assert {p.external_id for p in contents.new} == {"good"}
    assert {p.external_id for p in contents.quarantined} == {"dead"}


def test_other_verticals_are_excluded(migrated_engine: Engine) -> None:
    grid = _employer(migrated_engine, vertical="grid_power_software", name="GridCo")
    avia = _employer(migrated_engine, vertical="aviation_software", name="AirCo")
    prof = _profile(migrated_engine)
    now = datetime(2026, 6, 16, tzinfo=UTC)
    g1 = _posting(migrated_engine, grid, "g1", first_seen=now)
    _posting(migrated_engine, avia, "a1", first_seen=now)
    _match(migrated_engine, g1, prof)

    contents = build_digest(migrated_engine, "grid_power_software", profile=prof, verify=_PASS)

    assert {p.external_id for p in contents.new} == {"g1"}


def test_last_sent_at_is_per_recipient(migrated_engine: Engine) -> None:
    t1 = datetime(2026, 6, 10, tzinfo=UTC)
    t2 = datetime(2026, 6, 14, tzinfo=UTC)
    _digest(migrated_engine, vertical="grid_power_software", status="sent", sent_at=t1)
    _digest(migrated_engine, vertical="grid_power_software", status="sent", sent_at=t2)
    _digest(migrated_engine, vertical="grid_power_software", status="pending", sent_at=None)
    _digest(
        migrated_engine,
        vertical="aviation_software",
        status="sent",
        sent_at=datetime(2026, 6, 15, tzinfo=UTC),
    )

    assert last_sent_at(migrated_engine, "grid_power_software", _EMAIL) == t2
    # A different recipient has no sent digest yet — its window is independent (D-027).
    assert last_sent_at(migrated_engine, "grid_power_software", "other@example.com") is None
    assert last_sent_at(migrated_engine, "nonexistent", _EMAIL) is None
