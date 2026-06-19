"""Integration tests for the extraction run (P5.2) — migrated SQLite, faked LLM + Workday detail.

Pins the selection contract: only open, in-scope (Stage A), not-yet-extracted postings extract;
out-of-scope and already-extracted are skipped; other verticals excluded; Workday goes through the
detail resolver; fields persist; the run is idempotent; a content change re-opens extraction.
"""

from datetime import UTC, datetime
from typing import Any, cast

from anthropic import Anthropic
from sqlalchemy import Engine, select

from vja.db import postings as postings_repo
from vja.db.engine import begin
from vja.db.schema import employers, postings
from vja.extract import ExtractedFields, run_extraction
from vja.models import Level, RemoteType
from vja.scope import ScopeConfig

_SCOPE = ScopeConfig(role_include=("engineer", "software", "data"), exclude=("senior", "sales"))
_NOW = datetime(2026, 6, 19, tzinfo=UTC)
_FIELDS = ExtractedFields(
    level=Level.NEW_GRAD, location="Houston, TX", remote=RemoteType.HYBRID, stack=["Python"]
)


class _FakeMessages:
    def parse(self, **kwargs: Any) -> Any:
        class _U:
            input_tokens = 800
            output_tokens = 120

        class _R:
            parsed_output = _FIELDS
            usage = _U()

        return _R()


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


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
    engine: Engine, employer_id: int, external_id: str, title: str, *, extracted: bool = False
) -> None:
    with begin(engine) as conn:
        conn.execute(
            postings.insert().values(
                employer_id=employer_id,
                external_id=external_id,
                content_hash=f"h-{external_id}",
                raw_payload={"description": f"{title} — build software."},
                title=title,
                status="open",
                first_seen_at=_NOW,
                last_seen_at=_NOW,
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
        client=cast("Anthropic", _FakeClient()),
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
    assert detail_calls == ["/job/data-eng"]  # Workday detail fetched once, with the externalPath

    swe = _row(migrated_engine, "swe")
    assert swe["level"] == "new_grad" and swe["remote"] == "hybrid" and swe["stack"] == ["Python"]
    assert swe["extracted_at"] is not None and swe["extraction_model"] == "claude-haiku-4-5"

    assert _row(migrated_engine, "/job/data-eng")["extracted_at"] is not None  # workday extracted

    assert _row(migrated_engine, "sales")["extracted_at"] is None  # out-of-scope untouched
    assert _row(migrated_engine, "plat")["extraction_model"] == "old"  # already-extracted untouched
    assert _row(migrated_engine, "avia-swe")["extracted_at"] is None  # other vertical untouched


def test_rerun_is_idempotent(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    _run(migrated_engine)
    summary, _ = _run(migrated_engine)
    assert (summary.total, summary.extracted) == (0, 0)  # nothing left to extract


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
