"""Integration tests for the extraction run (P5.2) — migrated SQLite, faked LLM + Workday detail.

Pins the selection contract: only open, in-scope (Stage A), not-yet-extracted postings extract;
out-of-scope and already-extracted are skipped; other verticals excluded; Workday goes through the
detail resolver; fields persist; the run is idempotent; a content change re-opens extraction.
"""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Engine, select

from vja.db import postings as postings_repo
from vja.db.engine import begin
from vja.db.schema import employers, postings
from vja.extract import ExtractedFields, run_extraction
from vja.llm import StructuredLLM, StructuredResult
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
    assert summary.est_cost_usd > 0
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
            conn, _row(migrated_engine, "swe")["employer_id"], "swe", "h-new", {"d": "new"}, _NOW
        )
    assert _row(migrated_engine, "swe")["extracted_at"] is None
    summary, _ = _run(migrated_engine)
    assert summary.extracted == 1  # the changed posting re-extracted
