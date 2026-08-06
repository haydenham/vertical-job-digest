"""Integration tests for digest assembly + the verification gate (P3B1, P5.4 rationale).

Real migrated SQLite; employers/postings/profiles/matches/digests seeded directly; verification
faked (a `Callable[[str], bool]`) so no network. Pins the window logic, the baseline rule, vertical
isolation, dead-link quarantine, and the P5.4 match-gating: a `new` posting appears only if it has
a relevant match (verdict maybe/yes/strong_yes) for *this* profile, ordered by score descending.
"""

from datetime import UTC, datetime, timedelta

import httpx
import respx
from sqlalchemy import Engine

from vja.db.engine import begin
from vja.db.matches import save_match
from vja.db.profiles import Profile, active_profiles, upsert_profile
from vja.db.schema import digests, employers, postings
from vja.digest.assembly import build_digest, last_sent_at
from vja.digest.verification import ApplyLinkVerifier

_PASS = lambda _url: True  # noqa: E731  (tiny test stub; a def would be noisier)
_EMAIL = "me@example.com"
# Later than every fixture date below (2026-06-10..17) and inside the D-109 age floor, so the
# floor is live in these tests without being what they are about.
_NOW = datetime(2026, 6, 18, tzinfo=UTC)


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
    trigger: str = "nightly",
    created_at: datetime | None = None,
) -> None:
    with begin(engine) as conn:
        save_match(
            conn,
            posting_id,
            profile.id,
            profile.resume_version,
            {"verdict": verdict, "score": score, "fits": "[]", "gaps": "[]", "rationale": "ok"},
            model="claude-sonnet-4-6",
            trigger=trigger,
            now=created_at or datetime.now(UTC),
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

    contents = build_digest(
        migrated_engine, "grid_power_software", profile=prof, now=_NOW, verify=_PASS
    )

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

    contents = build_digest(
        migrated_engine, "grid_power_software", profile=prof, now=_NOW, verify=_PASS
    )

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

    contents = build_digest(
        migrated_engine, "grid_power_software", profile=prof, now=_NOW, verify=_PASS
    )

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
    # Match times are explicit: each posting was matched by the run that first saw it, so this
    # pins the plain window and not the D-103 late-match case (below).
    _match(migrated_engine, old_open, prof, created_at=before)
    _match(migrated_engine, new_open, prof, created_at=after)

    contents = build_digest(
        migrated_engine, "grid_power_software", profile=prof, now=_NOW, since=cutoff, verify=_PASS
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
    _match(migrated_engine, old, prof, created_at=cutoff - timedelta(days=1))
    _match(migrated_engine, fresh, prof, created_at=cutoff + timedelta(days=1))

    contents = build_digest(
        migrated_engine, "grid_power_software", profile=prof, now=_NOW, verify=_PASS
    )

    assert contents.since == cutoff
    assert {p.external_id for p in contents.new} == {"fresh"}


def test_match_landing_after_the_send_is_not_lost(migrated_engine: Engine) -> None:
    """A pipeline match written *after* the digest that covered its `first_seen_at` still ships.

    The D-103 regression: the pipeline (every 4h) and the digest (06:00) are separate Jobs, so a
    posting can be first seen at 05:30, be matched at 06:20, and find that the 06:00 digest already
    advanced `last_sent_at` past its `first_seen_at`. Windowing on `first_seen_at` alone drops it
    from every future digest while the dashboard shows it — the reported bug.
    """
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    first_seen = datetime(2026, 6, 16, 5, 30, tzinfo=UTC)
    sent = datetime(2026, 6, 16, 6, 0, tzinfo=UTC)
    matched = datetime(2026, 6, 16, 6, 20, tzinfo=UTC)

    late = _posting(migrated_engine, emp, "late-match", first_seen=first_seen)
    _digest(migrated_engine, vertical="grid_power_software", status="sent", sent_at=sent)
    _match(migrated_engine, late, prof, created_at=matched, trigger="nightly")

    contents = build_digest(
        migrated_engine, "grid_power_software", profile=prof, now=_NOW, verify=_PASS
    )

    assert contents.since == sent
    assert {p.external_id for p in contents.new} == {"late-match"}


def test_backfill_matches_do_not_resurface_old_postings(migrated_engine: Engine) -> None:
    """A recent *backfill* match over an old posting stays out — the re-upload flood guard.

    A resume re-upload or vertical switch re-matches up to `VJA_BACKFILL_MAX_POSTINGS` postings
    with a fresh `created_at` regardless of age. Only `trigger=nightly` earns the match-time window;
    otherwise one re-upload mails the user a digest of roles they have already seen.
    """
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    sent = datetime(2026, 6, 16, 6, 0, tzinfo=UTC)
    old = _posting(migrated_engine, emp, "old", first_seen=sent - timedelta(days=30))
    _digest(migrated_engine, vertical="grid_power_software", status="sent", sent_at=sent)
    _match(migrated_engine, old, prof, created_at=sent + timedelta(hours=1), trigger="backfill")

    contents = build_digest(
        migrated_engine, "grid_power_software", profile=prof, now=_NOW, verify=_PASS
    )

    assert contents.new == []


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
        now=_NOW,
        verify=lambda url: url != "https://dead/2",
    )

    assert {p.external_id for p in contents.new} == {"good"}
    assert {p.external_id for p in contents.quarantined} == {"dead"}


@respx.mock
def test_the_real_verifier_quarantines_only_the_dead_link(migrated_engine: Engine) -> None:
    """End to end through `ApplyLinkVerifier`, not a `Callable` stub (D-110).

    The unit tests pin the classifier; this pins the wiring — that a `DEAD` result still reaches
    `contents.quarantined` while a block and an unreachable host now reach `contents.new`. Those
    last two are the ~21% of matched roles the digest was silently dropping.
    """
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    now = datetime(2026, 6, 16, tzinfo=UTC)
    urls = {
        "good": "https://ok.example.com/1",
        "gone": "https://gone.example.com/2",
        "blocked": "https://waf.example.com/3",
        "flaky": "https://flaky.example.com/4",
    }
    for external_id, url in urls.items():
        _match(
            migrated_engine,
            _posting(migrated_engine, emp, external_id, first_seen=now, apply_url=url),
            prof,
        )
    respx.head(urls["good"]).mock(return_value=httpx.Response(200))
    respx.head(urls["gone"]).mock(return_value=httpx.Response(404))
    respx.head(urls["blocked"]).mock(return_value=httpx.Response(403))
    respx.head(urls["flaky"]).mock(return_value=httpx.Response(429))

    with ApplyLinkVerifier(httpx.Client(), sleep=lambda _s: None) as verify:
        contents = build_digest(
            migrated_engine, "grid_power_software", profile=prof, now=_NOW, verify=verify
        )

    assert {p.external_id for p in contents.new} == {"good", "blocked", "flaky"}
    assert {p.external_id for p in contents.quarantined} == {"gone"}


def test_other_verticals_are_excluded(migrated_engine: Engine) -> None:
    grid = _employer(migrated_engine, vertical="grid_power_software", name="GridCo")
    avia = _employer(migrated_engine, vertical="aviation_software", name="AirCo")
    prof = _profile(migrated_engine)
    now = datetime(2026, 6, 16, tzinfo=UTC)
    g1 = _posting(migrated_engine, grid, "g1", first_seen=now)
    _posting(migrated_engine, avia, "a1", first_seen=now)
    _match(migrated_engine, g1, prof)

    contents = build_digest(
        migrated_engine, "grid_power_software", profile=prof, now=_NOW, verify=_PASS
    )

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


# --- the age floor (D-109) --------------------------------------------------------------------


def test_a_posting_past_the_age_floor_is_never_mailed(migrated_engine: Engine) -> None:
    """The digest and the dashboard must agree. Without this the digest would mail a role the
    dashboard refuses to show, which is worse than either behaviour on its own.

    The window normally hides old roles anyway; the case that needs the floor is a *wide* window —
    here a first digest (`since is None`), which is also what a paused-then-resumed user gets when
    they come back (D-094).
    """
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    fresh = _posting(migrated_engine, emp, "fresh", first_seen=_NOW - timedelta(days=2))
    stale = _posting(migrated_engine, emp, "stale", first_seen=_NOW - timedelta(days=90))
    _match(migrated_engine, fresh, prof)
    _match(migrated_engine, stale, prof)

    contents = build_digest(
        migrated_engine, "grid_power_software", profile=prof, now=_NOW, verify=_PASS
    )

    assert contents.since is None  # the widest window there is
    assert {p.external_id for p in contents.new} == {"fresh"}


def test_the_age_floor_does_not_suppress_a_closure(migrated_engine: Engine) -> None:
    """Closures are exempt. A role that genuinely vanished is worth reporting however old it was —
    the floor exists to stop us *advertising* stale roles, not to hide that one ended.
    """
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    since = _NOW - timedelta(days=1)
    _digest(migrated_engine, vertical="grid_power_software", status="sent", sent_at=since)
    _posting(
        migrated_engine,
        emp,
        "long_lived",
        first_seen=_NOW - timedelta(days=200),
        status="closed",
        closed_at=_NOW,
    )

    contents = build_digest(
        migrated_engine, "grid_power_software", profile=prof, now=_NOW, verify=_PASS
    )

    assert {p.external_id for p in contents.closed} == {"long_lived"}
