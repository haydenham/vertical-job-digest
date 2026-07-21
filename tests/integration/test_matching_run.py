"""Integration tests for the matching run (P5.3) — migrated SQLite, faked LLM.

Pins the selection contract: only open, extracted, in-scope (Stage A), Stage-B-surviving postings
with no existing match for the active resume get matched; out-of-scope, unextracted, senior,
non-US, other-vertical, and already-matched postings are skipped; the run is idempotent; one
posting's failure is isolated; cost is summed; multiple active profiles are each matched.
"""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Engine, func, select

from vja.db.engine import begin
from vja.db.profiles import upsert_profile
from vja.db.schema import employers, matches, postings
from vja.llm import StructuredLLM, StructuredResult
from vja.match import MatchResult, run_matching
from vja.models import TokenUsage, Verdict
from vja.scope import ScopeConfig
from vja.verticals import VerticalConfig

_NOW = datetime(2026, 6, 19, tzinfo=UTC)
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
    def __init__(
        self,
        fail_titles: frozenset[str] = frozenset(),
        result_payload: dict[str, Any] | None = None,
    ) -> None:
        self._fail_titles = fail_titles
        self._result_payload = result_payload
        self.calls = 0

    def parse(self, **kwargs: Any) -> StructuredResult[MatchResult]:
        self.calls += 1
        content = kwargs["user"]
        if any(t in content for t in self._fail_titles):
            raise ValueError("LLM returned no structured content")
        elif self._result_payload is not None:
            parsed = kwargs["response_model"].model_validate(self._result_payload)
        else:
            parsed = _RESULT
        return StructuredResult(
            value=parsed,
            usage=TokenUsage(input=900, output=150),
            cost_usd=0.00495,
            model="claude-sonnet-4-6-actual",
            latency_seconds=0.1,
        )


def _employer(engine: Engine, *, vertical: str, name: str) -> int:
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical=vertical,
                name=name,
                ats_type="greenhouse",
                ats_slug=name.lower(),
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
    level: str = "new_grad",
    location: str = "Houston, TX",
    extracted: bool = True,
) -> None:
    with begin(engine) as conn:
        conn.execute(
            postings.insert().values(
                employer_id=employer_id,
                external_id=external_id,
                content_hash=f"h-{external_id}",
                raw_payload={},
                title=title,
                level=level if extracted else None,
                location=location if extracted else None,
                stack=["Python"] if extracted else None,
                status="open",
                first_seen_at=_NOW,
                last_seen_at=_NOW,
                extracted_at=_NOW if extracted else None,
                extraction_model="claude-haiku-4-5" if extracted else None,
            )
        )


def _seed(engine: Engine) -> int:
    gridco = _employer(engine, vertical=_VERTICAL, name="GridCo")
    avia = _employer(engine, vertical="aviation_software", name="AirCo")
    _posting(engine, gridco, "swe", "Software Engineer")  # in-scope, early-career, US → match
    _posting(engine, gridco, "sales", "Senior Sales Lead")  # out-of-scope title → Stage A skip
    _posting(engine, gridco, "sr", "Software Engineer", level="senior")  # Stage B level → skip
    _posting(engine, gridco, "uk", "Data Engineer", location="London, UK")  # Stage B geo → skip
    _posting(engine, gridco, "raw", "Platform Engineer", extracted=False)  # unextracted → skip
    _posting(engine, avia, "avia", "Software Engineer")  # other vertical → skip
    return upsert_profile(
        engine,
        user_email=_CONFIG.user_email,
        vertical=_VERTICAL,
        resume_text=_CONFIG.resume_text,
        domain_vocabulary=_CONFIG.domain_vocabulary,
    )


def _match_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(matches)).scalar_one())


def _run(engine: Engine, client: _FakeClient | None = None):  # type: ignore[no-untyped-def]
    return run_matching(
        engine,
        _VERTICAL,
        config=_CONFIG,
        client=cast("StructuredLLM", client or _FakeClient()),
        now=_NOW,
    )


def test_matches_only_in_scope_stage_b_survivors(migrated_engine: Engine) -> None:
    profile_id = _seed(migrated_engine)
    summary = _run(migrated_engine)

    assert (summary.profiles, summary.total, summary.matched, summary.failed) == (1, 1, 1, 0)
    assert summary.est_cost_usd is not None and summary.est_cost_usd > 0
    assert summary.usage.input == 900  # real tokens aggregated through the run (D-069)
    assert _match_count(migrated_engine) == 1

    with migrated_engine.connect() as conn:
        row = conn.execute(select(matches)).mappings().one()
    assert row["profile_id"] == profile_id
    assert row["verdict"] == "yes" and row["score"] == 70
    assert row["trigger"] == "nightly"
    assert row["model_version"] == "claude-sonnet-4-6-actual"  # upstream response, not route


def test_rerun_is_idempotent(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    _run(migrated_engine)
    summary = _run(migrated_engine)
    assert (summary.total, summary.matched) == (0, 0)  # nothing left to match
    assert _match_count(migrated_engine) == 1


def test_per_posting_failure_is_isolated(migrated_engine: Engine) -> None:
    # Two in-scope survivors; one is made to fail parsing — it must not abort the other.
    _seed(migrated_engine)
    with begin(migrated_engine) as conn:
        gridco = int(
            conn.execute(select(employers.c.id).where(employers.c.name == "GridCo")).scalar_one()
        )
    _posting(migrated_engine, gridco, "swe2", "Backend Engineer")

    summary = _run(migrated_engine, _FakeClient(fail_titles=frozenset({"Backend Engineer"})))
    assert summary.total == 2
    assert summary.matched == 1 and summary.failed == 1  # one parsed, one isolated
    assert _match_count(migrated_engine) == 1


def test_out_of_range_score_is_saved_once_at_boundary(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    payload = _RESULT.model_dump()

    first = _run(migrated_engine, _FakeClient(result_payload={**payload, "score": -1}))
    second = _run(migrated_engine)

    assert (first.total, first.matched, first.failed) == (1, 1, 0)
    assert second.total == 0  # persisted result is not billed/retried on the next run
    with migrated_engine.connect() as conn:
        row = conn.execute(select(matches.c.score)).one()
    assert row.score == 0


def test_multiple_active_profiles_each_match(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    # A second user with a distinct resume → a separate active profile for the same vertical.
    upsert_profile(
        migrated_engine,
        user_email="second@example.com",
        vertical=_VERTICAL,
        resume_text="A different early-career resume.",
        domain_vocabulary=_CONFIG.domain_vocabulary,
    )
    summary = _run(migrated_engine)
    assert summary.profiles == 2
    assert summary.total == 2 and summary.matched == 2  # the one survivor matched per profile
    assert _match_count(migrated_engine) == 2
