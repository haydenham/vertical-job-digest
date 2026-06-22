"""Integration tests for the one-time corpus repair (WS5 / D-043) — migrated SQLite, no LLM.

Pins `repair_vertical`: location is re-derived from `raw_payload` per ATS and written
L1-authoritatively (a null snapshot never nulls a model fill), `in_scope` is recomputed for the
extracted rows, matches whose posting now fails Stage B are deleted, and the run is idempotent.
"""

from datetime import UTC, datetime

from sqlalchemy import Engine, select

from vja.db.engine import begin
from vja.db.matches import save_match
from vja.db.profiles import Profile, active_profiles, upsert_profile
from vja.db.schema import employers, matches, postings
from vja.prefilter import PrefilterConfig
from vja.repair import repair_vertical

_NOW = datetime(2026, 6, 22, tzinfo=UTC)
_VERTICAL = "grid_power_software"
_PREFILTER = PrefilterConfig(locations=("US",), levels=("intern", "new_grad", "early_career"))


def _employer(engine: Engine, *, name: str, ats: str) -> int:
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical=_VERTICAL,
                name=name,
                ats_type=ats,
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
    *,
    raw_payload: dict,  # type: ignore[type-arg]
    location: str | None,
    level: str | None = "new_grad",
    extracted: bool = True,
) -> int:
    with begin(engine) as conn:
        result = conn.execute(
            postings.insert().values(
                employer_id=employer_id,
                external_id=external_id,
                content_hash=f"h-{external_id}",
                raw_payload=raw_payload,
                title="Software Engineer",
                location=location,
                level=level,
                status="open",
                first_seen_at=_NOW,
                last_seen_at=_NOW,
                extracted_at=_NOW if extracted else None,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _profile(engine: Engine) -> Profile:
    upsert_profile(
        engine,
        user_email="me@example.com",
        vertical=_VERTICAL,
        resume_text="r",
        domain_vocabulary=[],
    )
    return next(p for p in active_profiles(engine, _VERTICAL))


def _match(engine: Engine, posting_id: int, profile: Profile, verdict: str) -> None:
    with begin(engine) as conn:
        save_match(
            conn,
            posting_id,
            profile.id,
            profile.resume_version,
            {"verdict": verdict, "score": 50, "fits": "[]", "gaps": "[]", "rationale": "ok"},
            model="claude-sonnet-4-6",
            trigger="nightly",
            now=_NOW,
        )


def _row(engine: Engine, external_id: str) -> dict:  # type: ignore[type-arg]
    with engine.connect() as conn:
        return dict(
            conn.execute(select(postings).where(postings.c.external_id == external_id))
            .mappings()
            .one()
        )


def _has_match(engine: Engine, posting_id: int) -> bool:
    with engine.connect() as conn:
        return (
            conn.execute(select(matches.c.id).where(matches.c.posting_id == posting_id)).first()
            is not None
        )


def _seed(engine: Engine) -> tuple[Profile, dict[str, int]]:
    prof = _profile(engine)
    wd = _employer(engine, name="WdCo", ats="workday")
    gh = _employer(engine, name="GhCo", ats="greenhouse")
    ids = {
        # Clobbered foreign Workday role: locationsText present, location NULL, matched while blind.
        "wd_foreign": _posting(
            engine,
            wd,
            "wd_foreign",
            raw_payload={"locationsText": "Mumbai, India"},
            location=None,
            level="early_career",
        ),
        # Clobbered US Greenhouse role: location.name present, location NULL.
        "gh_us": _posting(
            engine, gh, "gh_us", raw_payload={"location": {"name": "Austin, TX"}}, location=None
        ),
        # Legit model fill: L1 snapshot has no location, the model filled it — must NOT be nulled.
        "gh_modelfill": _posting(engine, gh, "gh_modelfill", raw_payload={}, location="Denver, CO"),
        # Not-yet-extracted: location re-derived, but in_scope stays NULL.
        "gh_unextracted": _posting(
            engine,
            gh,
            "gh_unextracted",
            raw_payload={"location": {"name": "Boston, MA"}},
            location=None,
            extracted=False,
        ),
    }
    _match(engine, ids["wd_foreign"], prof, "maybe")  # stale — should be deleted
    _match(engine, ids["gh_us"], prof, "yes")  # legit — should survive
    _match(engine, ids["gh_modelfill"], prof, "yes")  # legit — should survive
    return prof, ids


def test_repair_restores_location_recomputes_scope_and_drops_stale_matches(
    migrated_engine: Engine,
) -> None:
    _, ids = _seed(migrated_engine)
    summary = repair_vertical(migrated_engine, _VERTICAL, prefilter=_PREFILTER)

    # Locations re-derived from raw_payload (the model fill is left alone).
    assert _row(migrated_engine, "wd_foreign")["location"] == "Mumbai, India"
    assert _row(migrated_engine, "gh_us")["location"] == "Austin, TX"
    assert _row(migrated_engine, "gh_modelfill")["location"] == "Denver, CO"  # not nulled
    assert _row(migrated_engine, "gh_unextracted")["location"] == "Boston, MA"

    # in_scope recomputed on the repaired location (foreign → False; US → True; unextracted → NULL).
    assert _row(migrated_engine, "wd_foreign")["in_scope"] is False
    assert _row(migrated_engine, "gh_us")["in_scope"] is True
    assert _row(migrated_engine, "gh_modelfill")["in_scope"] is True
    assert _row(migrated_engine, "gh_unextracted")["in_scope"] is None

    # The foreign match is deleted; the two legit ones survive.
    assert not _has_match(migrated_engine, ids["wd_foreign"])
    assert _has_match(migrated_engine, ids["gh_us"])
    assert _has_match(migrated_engine, ids["gh_modelfill"])

    assert (summary.locations_repaired, summary.in_scope_true, summary.in_scope_false) == (3, 2, 1)
    assert summary.matches_deleted == 1


def test_repair_is_idempotent(migrated_engine: Engine) -> None:
    _seed(migrated_engine)
    repair_vertical(migrated_engine, _VERTICAL, prefilter=_PREFILTER)
    second = repair_vertical(migrated_engine, _VERTICAL, prefilter=_PREFILTER)
    assert (second.locations_repaired, second.matches_deleted) == (0, 0)
    assert (second.in_scope_true, second.in_scope_false) == (2, 1)  # recomputed, unchanged
