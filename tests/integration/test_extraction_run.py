"""Integration tests for the extraction run (P5.2) — migrated SQLite, faked LLM + Workday detail.

Pins the selection contract: only open, in-scope (Stage A), not-yet-extracted postings extract;
out-of-scope and already-extracted are skipped; other verticals excluded; Workday goes through the
detail resolver; fields persist; the run is idempotent; a content change re-opens extraction.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import Engine, select

from vja.db import postings as postings_repo
from vja.db.engine import begin
from vja.db.schema import employers, postings
from vja.extract import _MAX_CONSECUTIVE_FAILURES, ExtractedFields, run_extraction
from vja.llm import StructuredLLM, StructuredOutputError, StructuredResult
from vja.models import Level, RemoteType, TokenUsage
from vja.prefilter import PrefilterConfig
from vja.scope import ScopeConfig

_SCOPE = ScopeConfig(role_include=("engineer", "software", "data"), exclude=("senior", "sales"))
_PREFILTER = PrefilterConfig(locations=("US",), levels=("intern", "new_grad", "early_career"))
_NOW = datetime(2026, 6, 19, tzinfo=UTC)
_FIELDS = ExtractedFields(
    level=Level.NEW_GRAD, location="Houston, TX", remote=RemoteType.HYBRID, stack=["Python"]
)


class _FakeClient:
    def parse(self, **kwargs: Any) -> StructuredResult[ExtractedFields]:
        return _structured(_FIELDS)


def _structured(fields: ExtractedFields) -> StructuredResult[ExtractedFields]:
    return StructuredResult(
        value=fields,
        usage=TokenUsage(input=800, output=120),
        cost_usd=0.0014,
        model="claude-haiku-4-5-actual",
        latency_seconds=0.1,
    )


def _detail_resolver_factory() -> tuple[Any, list[str]]:
    calls: list[str] = []

    def resolver(employer: Any, external_path: str) -> dict[str, Any]:
        calls.append(external_path)
        return {"jobDescription": "Grid data engineering role.", "startDate": "2026-06-01"}

    return resolver, calls


def _employer(engine: Engine, *, vertical: str, name: str, ats: str) -> int:
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical=vertical,
                name=name,
                ats_type=ats,
                ats_slug=name.lower(),
                endpoint="https://x.wd5.myworkdayjobs.com/wday/cxs/x/site/jobs"
                if ats == "workday"
                else None,
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
    extracted: bool = False,
    source_updated_at: datetime | None = None,
    location: str | None = None,
    description: str | None = None,
) -> None:
    with begin(engine) as conn:
        conn.execute(
            postings.insert().values(
                employer_id=employer_id,
                external_id=external_id,
                content_hash=f"h-{external_id}",
                raw_payload={"description": f"{title} — build software."},
                title=title,
                location=location,
                status="open",
                first_seen_at=_NOW,
                last_seen_at=_NOW,
                source_updated_at=source_updated_at,
                description=description,
                extracted_at=_NOW if extracted else None,
                extraction_model="old" if extracted else None,
            )
        )


def _row(engine: Engine, external_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        return dict(
            conn.execute(select(postings).where(postings.c.external_id == external_id))
            .mappings()
            .one()
        )


def _run(engine: Engine):  # type: ignore[no-untyped-def]
    resolver, calls = _detail_resolver_factory()
    summary = run_extraction(
        engine,
        "grid_power_software",
        scope=_SCOPE,
        prefilter=_PREFILTER,
        client=cast("StructuredLLM", _FakeClient()),
        resolve_detail=resolver,
        now=_NOW,
    )
    return summary, calls


def _seed(engine: Engine) -> None:
    gh = _employer(engine, vertical="grid_power_software", name="GridCo", ats="greenhouse")
    wd = _employer(engine, vertical="grid_power_software", name="WdCo", ats="workday")
    avia = _employer(engine, vertical="aviation_software", name="AirCo", ats="greenhouse")
    _posting(engine, gh, "swe", "Software Engineer")  # in-scope, unextracted → extract
    _posting(engine, gh, "sales", "Senior Sales Lead")  # out-of-scope → skip
    _posting(engine, wd, "/job/data-eng", "Data Engineer")  # in-scope workday → extract via detail
    _posting(engine, gh, "plat", "Platform Engineer", extracted=True)  # already extracted → skip
    _posting(engine, avia, "avia-swe", "Software Engineer")  # other vertical → skip


def test_extracts_only_in_scope_unextracted(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    summary, detail_calls = _run(migrated_engine)

    assert (summary.total, summary.extracted, summary.failed) == (2, 2, 0)
    assert summary.est_cost_usd is not None and summary.est_cost_usd > 0
    assert summary.usage.input == 1600  # 2 postings × 800 input tokens, aggregated (D-069)
    assert detail_calls == ["/job/data-eng"]  # Workday detail fetched once, with the externalPath

    swe = _row(migrated_engine, "swe")
    assert swe["level"] == "new_grad" and swe["remote"] == "hybrid" and swe["stack"] == ["Python"]
    assert swe["extracted_at"] is not None
    assert swe["extraction_model"] == "claude-haiku-4-5-actual"  # upstream response, not route

    assert _row(migrated_engine, "/job/data-eng")["extracted_at"] is not None  # workday extracted

    assert _row(migrated_engine, "sales")["extracted_at"] is None  # out-of-scope untouched
    assert _row(migrated_engine, "plat")["extraction_model"] == "old"  # already-extracted untouched
    assert _row(migrated_engine, "avia-swe")["extracted_at"] is None  # other vertical untouched


def test_rerun_is_idempotent(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    _run(migrated_engine)
    summary, _ = _run(migrated_engine)
    assert (summary.total, summary.extracted) == (0, 0)  # nothing left to extract


class _ClientReturning:
    """A fake LLM whose extraction always returns the given fields (with a `posted_at`)."""

    def __init__(self, fields: ExtractedFields) -> None:
        self._fields = fields

    def parse(self, **kwargs: Any) -> StructuredResult[ExtractedFields]:
        return _structured(self._fields)


def test_extraction_fills_source_updated_at_only_when_null(migrated_engine: Engine) -> None:
    # D-038: the extracted `posted_at` fills `source_updated_at` only where L1 left it NULL
    # (Workday); a clean L1 date is never overwritten by the model's body-read date.
    gh = _employer(migrated_engine, vertical="grid_power_software", name="GridCo", ats="greenhouse")
    existing = datetime(2026, 6, 10, tzinfo=UTC)
    _posting(migrated_engine, gh, "needs", "Software Engineer")  # source NULL → should fill
    _posting(migrated_engine, gh, "has", "Data Engineer", source_updated_at=existing)  # keep

    fields = ExtractedFields(
        level=Level.NEW_GRAD,
        remote=RemoteType.HYBRID,
        posted_at="2026-06-05T00:00:00Z",
    )
    run_extraction(
        migrated_engine,
        "grid_power_software",
        scope=_SCOPE,
        prefilter=_PREFILTER,
        client=cast("StructuredLLM", _ClientReturning(fields)),
        resolve_detail=_detail_resolver_factory()[0],
        now=_NOW,
    )

    assert _row(migrated_engine, "needs")["source_updated_at"] == datetime(2026, 6, 5, tzinfo=UTC)
    assert _row(migrated_engine, "has")["source_updated_at"] == existing  # unchanged


def test_extraction_fills_location_only_when_null(migrated_engine: Engine) -> None:
    # WS1 / L1-authoritative: the L1 location (e.g. Workday `locationsText` = "Mumbai, India") is
    # never overwritten by the model — extraction fills `location` only where L1 left it NULL. This
    # guards the clobber that blanked foreign locations and made Stage B + the matcher geo-blind.
    gh = _employer(migrated_engine, vertical="grid_power_software", name="GridCo", ats="greenhouse")
    _posting(migrated_engine, gh, "needs", "Software Engineer")  # location NULL → should fill
    _posting(migrated_engine, gh, "has", "Data Engineer", location="Mumbai, India")  # keep L1

    fields = ExtractedFields(level=Level.NEW_GRAD, location="Houston, TX", remote=RemoteType.HYBRID)
    run_extraction(
        migrated_engine,
        "grid_power_software",
        scope=_SCOPE,
        prefilter=_PREFILTER,
        client=cast("StructuredLLM", _ClientReturning(fields)),
        resolve_detail=_detail_resolver_factory()[0],
        now=_NOW,
    )

    assert _row(migrated_engine, "needs")["location"] == "Houston, TX"  # filled (L1 was NULL)
    assert _row(migrated_engine, "has")["location"] == "Mumbai, India"  # non-null L1 preserved


def test_extraction_stamps_in_scope_on_effective_location(migrated_engine: Engine) -> None:
    # WS2 (D-043): in_scope is the durable Stage-B gate, computed on the *effective* L1-authored
    # location. A US row → True; a foreign L1 location whose model read returns null → False (the
    # clobber case: in_scope must reflect "Mumbai", not the null the model gave).
    gh = _employer(migrated_engine, vertical="grid_power_software", name="GridCo", ats="greenhouse")
    _posting(migrated_engine, gh, "us", "Software Engineer", location="Austin, TX")
    _posting(migrated_engine, gh, "foreign", "Data Engineer", location="Mumbai, India")

    # Model returns no location (the real clobber pattern) — in_scope must use the stored L1 value.
    fields = ExtractedFields(level=Level.NEW_GRAD, location=None, remote=RemoteType.ONSITE)
    run_extraction(
        migrated_engine,
        "grid_power_software",
        scope=_SCOPE,
        prefilter=_PREFILTER,
        client=cast("StructuredLLM", _ClientReturning(fields)),
        resolve_detail=_detail_resolver_factory()[0],
        now=_NOW,
    )

    assert _row(migrated_engine, "us")["in_scope"] is True
    assert _row(migrated_engine, "foreign")["in_scope"] is False


def test_content_change_reopens_extraction(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    _run(migrated_engine)
    # A content change must clear the cache so the next pass re-extracts.
    with begin(migrated_engine) as conn:
        postings_repo.update_changed(
            conn,
            _row(migrated_engine, "swe")["employer_id"],
            "swe",
            "h-new",
            {"d": "new"},
            _NOW,
            description="A rewritten body.",
        )
    assert _row(migrated_engine, "swe")["extracted_at"] is None
    summary, _ = _run(migrated_engine)
    assert summary.extracted == 1  # the changed posting re-extracted


# --- stored description (D-095 PR 2) -----------------------------------------------------------


def test_list_only_ats_keeps_the_body_it_fetched_for_the_model(migrated_engine: Engine) -> None:
    # The Workday detail is fetched anyway to feed extraction; before D-095 it was then thrown
    # away, leaving those rows with no body at all.
    _seed(migrated_engine)

    _run(migrated_engine)

    assert _row(migrated_engine, "/job/data-eng")["description"] == "Grid data engineering role."


def test_extraction_does_not_touch_a_rich_list_bodys_row(migrated_engine: Engine) -> None:
    # Greenhouse & co. carry the body in the list, so L1 already stored it at insert; extraction
    # must leave it exactly as-is (the `location`/`source_updated_at` L1-authoritative rule).
    gh = _employer(migrated_engine, vertical="grid_power_software", name="GridCo", ats="greenhouse")
    _posting(migrated_engine, gh, "swe", "Software Engineer", description="The L1 body.")

    _run(migrated_engine)

    row = _row(migrated_engine, "swe")
    assert row["extracted_at"] == _NOW  # it really did extract
    assert row["description"] == "The L1 body."


def test_extraction_never_overwrites_an_existing_body(migrated_engine: Engine) -> None:
    # Same rule on the list-only path: a body already present wins over the detail read.
    wd = _employer(migrated_engine, vertical="grid_power_software", name="WdCo", ats="workday")
    _posting(
        migrated_engine, wd, "/job/data-eng", "Data Engineer", description="Body already stored."
    )

    _run(migrated_engine)

    assert _row(migrated_engine, "/job/data-eng")["description"] == "Body already stored."


def test_detail_body_is_normalized_to_plain_text(migrated_engine: Engine) -> None:
    wd = _employer(migrated_engine, vertical="grid_power_software", name="WdCo", ats="workday")
    _posting(migrated_engine, wd, "/job/data-eng", "Data Engineer")

    def resolver(employer: Any, external_path: str) -> dict[str, Any]:
        return {"jobDescription": "<p>Grid role.</p><ul><li>Python</li><li>SQL</li></ul>"}

    run_extraction(
        migrated_engine,
        "grid_power_software",
        scope=_SCOPE,
        prefilter=_PREFILTER,
        client=cast("StructuredLLM", _FakeClient()),
        resolve_detail=resolver,
        now=_NOW,
    )

    assert _row(migrated_engine, "/job/data-eng")["description"] == "Grid role.\n\nPython\nSQL"


class _AlwaysRejectsClient:
    """Every call reaches the provider, is billed, and then fails schema validation.

    The 2026-08-18 shape: the model answered every time, so this is not a transport failure and
    the tokens are on the invoice.
    """

    def __init__(self) -> None:
        self.calls = 0

    def parse(self, **kwargs: Any) -> StructuredResult[ExtractedFields]:
        self.calls += 1
        raise StructuredOutputError(
            model="claude-haiku-4-5-actual",
            usage=TokenUsage(input=800, output=120),
            cost_usd=0.0014,
        )


def _run_with(engine: Engine, client: Any):  # type: ignore[no-untyped-def]
    resolver, _ = _detail_resolver_factory()
    return run_extraction(
        engine,
        "grid_power_software",
        scope=_SCOPE,
        prefilter=_PREFILTER,
        client=cast("StructuredLLM", client),
        resolve_detail=resolver,
        now=_NOW,
    )


def test_systematic_validation_failure_trips_the_breaker_and_is_still_metered(
    migrated_engine: Engine,
) -> None:
    """A broken Layer 2 must cost one bounded batch, and must not report itself as free."""
    gh = _employer(migrated_engine, vertical="grid_power_software", name="GridCo", ats="greenhouse")
    for i in range(60):
        _posting(migrated_engine, gh, f"p{i}", "Software Engineer")

    client = _AlwaysRejectsClient()
    summary = _run_with(migrated_engine, client)

    assert summary.aborted is True
    assert client.calls == _MAX_CONSECUTIVE_FAILURES  # stopped early, did not walk the backlog
    assert summary.extracted == 0
    assert summary.failed == _MAX_CONSECUTIVE_FAILURES
    # The billed tokens are reported rather than silently dropped (the D-035 hole).
    assert summary.usage.input == 800 * _MAX_CONSECUTIVE_FAILURES
    assert summary.est_cost_usd == pytest.approx(0.0014 * _MAX_CONSECUTIVE_FAILURES)
    # Nothing was persisted: a failed extraction leaves the row for a later, working run.
    assert _row(migrated_engine, "p0")["extracted_at"] is None


def test_isolated_failures_do_not_trip_the_breaker(migrated_engine: Engine) -> None:
    """The breaker must only fire on a systemic fault, never on the odd bad posting."""

    class _FlakyClient:
        def __init__(self) -> None:
            self.calls = 0

        def parse(self, **kwargs: Any) -> StructuredResult[ExtractedFields]:
            self.calls += 1
            if self.calls % 3 == 0:  # a third fail, but never 20 in a row
                raise StructuredOutputError(
                    model="m", usage=TokenUsage(input=800, output=120), cost_usd=0.0014
                )
            return _structured(_FIELDS)

    gh = _employer(migrated_engine, vertical="grid_power_software", name="GridCo", ats="greenhouse")
    for i in range(30):
        _posting(migrated_engine, gh, f"p{i}", "Software Engineer")

    summary = _run_with(migrated_engine, _FlakyClient())

    assert summary.aborted is False
    assert summary.extracted == 20 and summary.failed == 10  # whole backlog walked


def test_a_posting_past_the_age_floor_is_never_extracted(migrated_engine: Engine) -> None:
    """D-109's argument, one stage earlier: don't pay to extract what can never be displayed.

    The boundary is pinned on both sides so the floor can't silently drift into an off-by-one.
    """
    gh = _employer(migrated_engine, vertical="grid_power_software", name="GridCo", ats="greenhouse")
    _posting(
        migrated_engine,
        gh,
        "fresh",
        "Software Engineer",
        source_updated_at=_NOW - timedelta(days=21),
    )
    _posting(
        migrated_engine,
        gh,
        "stale",
        "Software Engineer",
        source_updated_at=_NOW - timedelta(days=21, seconds=1),
    )

    summary = _run_with(migrated_engine, _FakeClient())

    assert (summary.total, summary.extracted) == (1, 1)  # exactly 21 days in, a second past is out
    assert _row(migrated_engine, "fresh")["extracted_at"] is not None
    assert _row(migrated_engine, "stale")["extracted_at"] is None
