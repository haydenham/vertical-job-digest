"""Integration tests for the signup backfill (P6 A2 / D-039) — migrated SQLite, faked LLM.

Pins the backfill contract: `run_backfill` matches one profile against open, extracted,
in-scope (Stage A) / Stage-B-surviving postings **within the 5-day activity window**, writing
`trigger=backfill`; older postings are skipped (the cap), and the run is idempotent. Nightly
matching's uncapped behavior is covered by `test_matching_run.py`.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import Engine, func, select

from vja.db.engine import begin
from vja.db.matches import count_matches_since, postings_needing_match
from vja.db.profiles import Profile, active_profiles, upsert_profile
from vja.db.schema import employers, matches, postings
from vja.llm import StructuredLLM, StructuredResult
from vja.match import (
    BackfillBudgetExceeded,
    MatchResult,
    check_backfill_budget,
    estimate_daily_backfill_spend,
    run_backfill,
)
from vja.models import MatchTrigger, TokenUsage, Verdict
from vja.scope import ScopeConfig
from vja.verticals import VerticalConfig

_NOW = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)  # window cutoff = _NOW − 5d = 2026-06-16 12:00
_VERTICAL = "grid_power_software"
_RESULT = MatchResult(verdict=Verdict.YES, score=70, fits=["fits"], gaps=["gaps"], rationale="ok")
_CONFIG = VerticalConfig(
    key=_VERTICAL,
    user_email="hayden@example.com",
    resume_text="Early-career grid software engineer. Python.",
    domain_vocabulary=("power markets", "dispatch optimization"),
    scope=ScopeConfig(role_include=("engineer", "software", "data"), exclude=("senior", "sales")),
    prefilter_locations=("US",),
    prefilter_levels=("intern", "new_grad", "early_career"),
)


class _FakeClient:
    def parse(self, **kwargs: Any) -> StructuredResult[MatchResult]:
        return StructuredResult(
            value=_RESULT,
            usage=TokenUsage(input=900, output=150),
            cost_usd=0.00495,
            model="claude-sonnet-4-6",
            latency_seconds=0.1,
        )


def _employer(engine: Engine, name: str = "GridCo") -> int:
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical=_VERTICAL,
                name=name,
                ats_type="greenhouse",
                ats_slug="gridco",
                source="manual",
                status="active",
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _posting(
    engine: Engine,
    employer_id: int,
    external_id: str,
    title: str,
    *,
    first_seen: datetime,
    source_updated: datetime | None,
    level: str = "new_grad",
) -> None:
    with begin(engine) as conn:
        conn.execute(
            postings.insert().values(
                employer_id=employer_id,
                external_id=external_id,
                content_hash=f"h-{external_id}",
                raw_payload={},
                title=title,
                level=level,
                location="Houston, TX",
                stack=["Python"],
                status="open",
                first_seen_at=first_seen,
                last_seen_at=first_seen,
                source_updated_at=source_updated,
                extracted_at=_NOW,
                extraction_model="claude-haiku-4-5",
            )
        )


def _seed(engine: Engine) -> Profile:
    grid = _employer(engine)
    _old = datetime(2026, 6, 1, tzinfo=UTC)
    # In window (≤5d): detected today, and updated 2d ago despite old detection.
    _posting(engine, grid, "recent", "Software Engineer", first_seen=_NOW, source_updated=None)
    _posting(
        engine,
        grid,
        "recent_su",
        "Data Engineer",
        first_seen=_old,
        source_updated=datetime(2026, 6, 19, tzinfo=UTC),
    )
    # Out of window: old on both the ATS date and the fallback detection date.
    _posting(engine, grid, "old", "Backend Engineer", first_seen=_old, source_updated=_old)
    _posting(
        engine, grid, "old_fallback", "Platform Engineer", first_seen=_old, source_updated=None
    )
    # In window but out of scope (Stage A) → still skipped.
    _posting(engine, grid, "sales", "Senior Sales Lead", first_seen=_NOW, source_updated=None)

    upsert_profile(
        engine,
        user_email=_CONFIG.user_email,
        vertical=_VERTICAL,
        resume_text=_CONFIG.resume_text,
        domain_vocabulary=_CONFIG.domain_vocabulary,
    )
    return active_profiles(engine, _VERTICAL)[0]  # the real profile, as the CLI resolves it


def _match_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(matches)).scalar_one())


def _write_matches(engine: Engine, profile: Profile, *, count: int, trigger: MatchTrigger) -> None:
    """Insert `count` already-decided matches for `profile` under `trigger`, skipping the model.

    The spend guard only ever counts rows, so the cheapest honest way to stage "a day with N
    matches on it" is to write them. Each needs its own posting, per
    `uq_matches_posting_profile_version`.
    """
    prefix = trigger.value
    employer_id = _employer(engine, name=f"GridCo-{prefix}")  # UNIQUE(vertical, name)
    with begin(engine) as conn:
        posting_ids: list[int] = []
        for i in range(count):
            result = conn.execute(
                postings.insert().values(
                    employer_id=employer_id,
                    external_id=f"{prefix}-{i}",
                    content_hash=f"h-{prefix}-{i}",
                    raw_payload={},
                    title="Software Engineer",
                    level="new_grad",
                    location="Houston, TX",
                    status="open",
                    first_seen_at=_NOW,
                    last_seen_at=_NOW,
                    extracted_at=_NOW,
                )
            )
            pk = result.inserted_primary_key
            assert pk is not None
            posting_ids.append(int(pk[0]))
        conn.execute(
            matches.insert(),
            [
                {
                    "posting_id": posting_id,
                    "profile_id": profile.id,
                    "resume_version": profile.resume_version,
                    "score": 70,
                    "verdict": Verdict.YES.value,
                    "model_version": "test",
                    "trigger": trigger.value,
                    "created_at": _NOW,
                }
                for posting_id in posting_ids
            ],
        )


def _run(engine: Engine, profile: Profile):  # type: ignore[no-untyped-def]
    return run_backfill(
        engine,
        _VERTICAL,
        profile,
        config=_CONFIG,
        client=cast("StructuredLLM", _FakeClient()),
        now=_NOW,
    )


def test_backfill_matches_only_recent_in_scope_postings(migrated_engine: Engine) -> None:
    profile = _seed(migrated_engine)
    summary = _run(migrated_engine, profile)

    # recent + recent_su match; old/old_fallback (out of window) and sales (out of scope) skipped.
    assert (summary.profiles, summary.total, summary.matched, summary.failed) == (1, 2, 2, 0)
    assert summary.est_cost_usd > 0
    assert _match_count(migrated_engine) == 2


def test_backfill_writes_trigger_backfill(migrated_engine: Engine) -> None:
    profile = _seed(migrated_engine)
    _run(migrated_engine, profile)
    with migrated_engine.connect() as conn:
        triggers = {r[0] for r in conn.execute(select(matches.c.trigger)).all()}
    assert triggers == {"backfill"}


def test_backfill_is_idempotent(migrated_engine: Engine) -> None:
    profile = _seed(migrated_engine)
    _run(migrated_engine, profile)
    summary = _run(migrated_engine, profile)
    assert (summary.total, summary.matched) == (0, 0)  # nothing left in the window to match
    assert _match_count(migrated_engine) == 2


# --- cost/abuse guards (P9.3 / D-057) --------------------------------------------------------


def test_backfill_caps_candidates_at_max_postings(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-signup cap (`VJA_BACKFILL_MAX_POSTINGS`) bounds the matched set, so one signup can't
    run away on cost. Five in-window, in-scope candidates exist; the cap of 2 stops at 2."""
    monkeypatch.setenv("VJA_BACKFILL_MAX_POSTINGS", "2")
    grid = _employer(migrated_engine)
    for i in range(5):
        _posting(
            migrated_engine,
            grid,
            f"role-{i}",
            f"Software Engineer {i}",
            first_seen=_NOW,
            source_updated=None,
        )
    upsert_profile(
        migrated_engine,
        user_email=_CONFIG.user_email,
        vertical=_VERTICAL,
        resume_text=_CONFIG.resume_text,
        domain_vocabulary=_CONFIG.domain_vocabulary,
    )
    profile = active_profiles(migrated_engine, _VERTICAL)[0]

    summary = _run(migrated_engine, profile)
    assert (summary.total, summary.matched) == (2, 2)
    assert _match_count(migrated_engine) == 2


def test_estimate_daily_backfill_spend_counts_todays_matches(migrated_engine: Engine) -> None:
    profile = _seed(migrated_engine)
    assert estimate_daily_backfill_spend(migrated_engine, _NOW) == 0.0
    _run(migrated_engine, profile)  # writes 2 backfill matches dated _NOW
    # 2 matches × the nominal $0.01/match proxy.
    assert estimate_daily_backfill_spend(migrated_engine, _NOW) == pytest.approx(0.02)


def test_check_backfill_budget_raises_when_over_ceiling(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VJA_DAILY_LLM_BUDGET_USD", "0")
    with pytest.raises(BackfillBudgetExceeded):
        check_backfill_budget(migrated_engine, _NOW)


def test_check_backfill_budget_passes_under_ceiling(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VJA_DAILY_LLM_BUDGET_USD", "5")
    profile = _seed(migrated_engine)
    _run(migrated_engine, profile)  # ~$0.02 estimated, well under $5
    check_backfill_budget(migrated_engine, _NOW)  # does not raise


def test_nightly_matches_do_not_consume_the_signup_ceiling(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The D-101 regression: a big nightly must not lock new users out of signup.

    Before the fix the ceiling counted *every* trigger, so a large nightly could exhaust the day's
    budget on spend the guard cannot prevent (the nightly is uncapped by design) and the refusal
    landed on a brand-new user at onboarding as a 429. On 2026-07-25 production wrote 397 nightly
    matches = $3.97 of a $5 ceiling with zero signups involved.
    """
    profile = _seed(migrated_engine)
    _write_matches(migrated_engine, profile, count=150, trigger=MatchTrigger.NIGHTLY)
    monkeypatch.setenv("VJA_DAILY_LLM_BUDGET_USD", "1")

    assert estimate_daily_backfill_spend(migrated_engine, _NOW) == 0.0
    check_backfill_budget(migrated_engine, _NOW)  # 150 nightly matches: still does not raise

    # The same volume on the backfill trigger is exactly what the ceiling is for.
    _write_matches(migrated_engine, profile, count=150, trigger=MatchTrigger.BACKFILL)
    assert estimate_daily_backfill_spend(migrated_engine, _NOW) == pytest.approx(1.5)
    with pytest.raises(BackfillBudgetExceeded):
        check_backfill_budget(migrated_engine, _NOW)


def test_count_matches_since_filters_by_trigger(migrated_engine: Engine) -> None:
    """The repo-level knob under the ceiling: filtered counts one trigger, unfiltered counts all.

    The default must keep counting everything — the spend guard is one caller, not the contract.
    """
    profile = _seed(migrated_engine)
    _write_matches(migrated_engine, profile, count=3, trigger=MatchTrigger.NIGHTLY)
    _write_matches(migrated_engine, profile, count=2, trigger=MatchTrigger.BACKFILL)
    midnight = _NOW.replace(hour=0, minute=0, second=0, microsecond=0)

    assert count_matches_since(migrated_engine, midnight) == 5
    assert count_matches_since(migrated_engine, midnight, trigger=MatchTrigger.NIGHTLY) == 3
    assert count_matches_since(migrated_engine, midnight, trigger=MatchTrigger.BACKFILL) == 2
    # The window still applies on top of the trigger filter.
    tomorrow = _NOW + timedelta(days=1)
    assert count_matches_since(migrated_engine, tomorrow, trigger=MatchTrigger.BACKFILL) == 0


def test_postings_needing_match_since_filters_to_window(migrated_engine: Engine) -> None:
    # The repo-level `since=` filter (what bounds the backfill) — Stage A/B is the caller's job,
    # so this returns every open∧extracted∧unmatched posting, windowed by the activity date.
    profile = _seed(migrated_engine)
    cutoff = _NOW - timedelta(days=5)

    uncapped = postings_needing_match(
        migrated_engine, _VERTICAL, profile.id, profile.resume_version, now=_NOW
    )
    windowed = postings_needing_match(
        migrated_engine, _VERTICAL, profile.id, profile.resume_version, now=_NOW, since=cutoff
    )

    assert {c.title for c in uncapped} == {
        "Software Engineer",
        "Data Engineer",
        "Backend Engineer",
        "Platform Engineer",
        "Senior Sales Lead",
    }
    # `old`/`old_fallback` drop out of the window; the recent ones (incl. out-of-scope sales) stay.
    assert {c.title for c in windowed} == {
        "Software Engineer",
        "Data Engineer",
        "Senior Sales Lead",
    }


# --- backfill completion stamp (D-082) --------------------------------------------------------


def test_backfill_stamps_completed_on_exit(migrated_engine: Engine) -> None:
    """run_backfill stamps backfill_completed_at when it finishes — the /api/me signal flips the
    dashboard banner from running to done."""
    from vja.db.profiles import backfill_stamps

    profile = _seed(migrated_engine)
    assert backfill_stamps(migrated_engine, profile.id) == (None, None)

    _run(migrated_engine, profile)
    _started, completed = backfill_stamps(migrated_engine, profile.id)
    assert completed is not None


def test_backfill_stamps_completed_even_when_every_match_fails(migrated_engine: Engine) -> None:
    """Per-posting isolation means a run whose every candidate errors still FINISHED — the
    completion stamp must land so the banner doesn't strand on running (D-082)."""
    from vja.db.profiles import backfill_stamps

    class _RaisingClient:
        def parse(self, **kwargs: Any) -> Any:
            raise RuntimeError("api down")

    profile = _seed(migrated_engine)
    summary = run_backfill(
        migrated_engine,
        _VERTICAL,
        profile,
        config=_CONFIG,
        client=cast("StructuredLLM", _RaisingClient()),
        now=_NOW,
    )
    assert (summary.matched, summary.failed) == (0, summary.total)
    _started, completed = backfill_stamps(migrated_engine, profile.id)
    assert completed is not None
