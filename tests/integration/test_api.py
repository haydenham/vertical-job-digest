"""Integration tests for the dashboard API (P6 B1 / D-041 / D-043) — FastAPI TestClient + SQLite.

The DB-level query logic is pinned in `test_dashboard_query.py`; this layer pins the HTTP plumbing:
param → query mapping (`window`, `view`), the `(vertical, profile_id)` profile resolution (default /
explicit / 404 / 409), the response envelope, and health.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlalchemy import Engine

from vja.api.app import create_app
from vja.db.engine import begin
from vja.db.matches import save_match
from vja.db.profiles import Profile, active_profiles, upsert_profile
from vja.db.schema import employers, postings

_NOW = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
_VERTICAL = "grid_power_software"


def _client(engine: Engine) -> TestClient:
    return TestClient(create_app(engine))


def _employer(engine: Engine, *, vertical: str = _VERTICAL, name: str = "GridCo") -> int:
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


def _posting(engine: Engine, employer_id: int, title: str, *, first_seen: datetime = _NOW) -> int:
    with begin(engine) as conn:
        result = conn.execute(
            postings.insert().values(
                employer_id=employer_id,
                external_id=title,
                content_hash=f"h-{title}",
                raw_payload={},
                title=title,
                apply_url=f"https://example.com/{title}",
                status="open",
                first_seen_at=first_seen,
                last_seen_at=first_seen,
                extracted_at=first_seen,
                in_scope=True,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _profile(engine: Engine, *, email: str = "me@example.com") -> Profile:
    upsert_profile(
        engine, user_email=email, vertical=_VERTICAL, resume_text=email, domain_vocabulary=[]
    )
    return next(p for p in active_profiles(engine, _VERTICAL) if p.user_email == email)


def _match(engine: Engine, posting_id: int, profile: Profile, *, verdict: str = "yes") -> None:
    with begin(engine) as conn:
        save_match(
            conn,
            posting_id,
            profile.id,
            profile.resume_version,
            {"verdict": verdict, "score": 70, "fits": "[]", "gaps": "[]", "rationale": "ok"},
            model="claude-sonnet-4-6",
            trigger="nightly",
            now=_NOW,
        )


def _titles(body: dict) -> list[str]:  # type: ignore[type-arg]
    return [p["title"] for p in body["postings"]]


def test_health(migrated_engine: Engine) -> None:
    resp = _client(migrated_engine).get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_cors_allows_dev_origin(migrated_engine: Engine) -> None:
    resp = _client(migrated_engine).get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_verticals_lists_active(migrated_engine: Engine) -> None:
    client = _client(migrated_engine)
    assert client.get("/api/verticals").json() == []  # none until a profile exists
    _profile(migrated_engine)
    assert client.get("/api/verticals").json() == [_VERTICAL]


def test_default_view_is_matched_only(migrated_engine: Engine) -> None:
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    matched = _posting(migrated_engine, emp, "matched")
    _posting(migrated_engine, emp, "unassessed")
    _match(migrated_engine, matched, prof)

    resp = _client(migrated_engine).get("/api/postings", params={"vertical": _VERTICAL})
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_id"] == prof.id
    assert body["window"] == "all"
    assert body["view"] == "matched"
    assert body["count"] == 1
    assert _titles(body) == ["matched"]


def test_cleaned_view_param(migrated_engine: Engine) -> None:
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    matched = _posting(migrated_engine, emp, "matched")
    _posting(migrated_engine, emp, "unassessed")
    _match(migrated_engine, matched, prof)

    resp = _client(migrated_engine).get(
        "/api/postings", params={"vertical": _VERTICAL, "view": "cleaned"}
    )
    assert resp.json()["view"] == "cleaned"
    assert set(_titles(resp.json())) == {"matched", "unassessed"}


def test_rejected_shown_in_cleaned_hidden_in_matched(migrated_engine: Engine) -> None:
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    matched = _posting(migrated_engine, emp, "matched")
    rejected = _posting(migrated_engine, emp, "rejected")
    _match(migrated_engine, matched, prof, verdict="yes")
    _match(migrated_engine, rejected, prof, verdict="no")

    client = _client(migrated_engine)
    assert _titles(client.get("/api/postings", params={"vertical": _VERTICAL}).json()) == [
        "matched"
    ]
    cleaned = client.get("/api/postings", params={"vertical": _VERTICAL, "view": "cleaned"})
    assert set(_titles(cleaned.json())) == {"matched", "rejected"}


@freeze_time(_NOW)
def test_new_today_window_param(migrated_engine: Engine) -> None:
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    today = _posting(migrated_engine, emp, "today", first_seen=_NOW)
    old = _posting(migrated_engine, emp, "old", first_seen=datetime(2026, 6, 1, tzinfo=UTC))
    _match(migrated_engine, today, prof)
    _match(migrated_engine, old, prof)

    resp = _client(migrated_engine).get(
        "/api/postings", params={"vertical": _VERTICAL, "window": "new_today"}
    )
    assert _titles(resp.json()) == ["today"]


def test_404_when_no_active_profile(migrated_engine: Engine) -> None:
    resp = _client(migrated_engine).get("/api/postings", params={"vertical": _VERTICAL})
    assert resp.status_code == 404


def test_409_when_multiple_active_profiles(migrated_engine: Engine) -> None:
    _profile(migrated_engine, email="a@example.com")
    _profile(migrated_engine, email="b@example.com")
    resp = _client(migrated_engine).get("/api/postings", params={"vertical": _VERTICAL})
    assert resp.status_code == 409


def test_explicit_profile_id_disambiguates(migrated_engine: Engine) -> None:
    p_a = _profile(migrated_engine, email="a@example.com")
    _profile(migrated_engine, email="b@example.com")
    emp = _employer(migrated_engine)
    matched = _posting(migrated_engine, emp, "for_a")
    _match(migrated_engine, matched, p_a)

    resp = _client(migrated_engine).get(
        "/api/postings", params={"vertical": _VERTICAL, "profile_id": p_a.id}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_id"] == p_a.id
    assert _titles(body) == ["for_a"]


def test_404_unknown_profile_id(migrated_engine: Engine) -> None:
    _profile(migrated_engine)
    resp = _client(migrated_engine).get(
        "/api/postings", params={"vertical": _VERTICAL, "profile_id": 99999}
    )
    assert resp.status_code == 404
