"""Integration tests for the dashboard API (P6 B1 / D-041 / D-043) — FastAPI TestClient + SQLite.

The DB-level query logic is pinned in `test_dashboard_query.py`; this layer pins the HTTP plumbing:
param → query mapping (`window`, `view`), the `(vertical, profile_id)` profile resolution (default /
explicit / 404 / 409), the response envelope, and health.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from sqlalchemy import Engine, select

from vja.api.app import create_app
from vja.api.auth import get_current_user, require_user
from vja.db.engine import begin
from vja.db.matches import save_match
from vja.db.profiles import (
    Profile,
    active_profiles,
    backfill_stamps,
    get_profile,
    mark_backfill_completed,
    mark_backfill_started,
    upsert_profile,
)
from vja.db.schema import employers, postings, profiles, users
from vja.db.users import User, upsert_user_by_google
from vja.resume import _MAX_CHARS as _MAX_RESUME_CHARS

# The real clock, not a fixed date: the endpoints apply the D-109 age floor against their own
# `datetime.now(UTC)`, so fixtures pinned to a 2026-06 literal would read as months old and
# every listing would come back empty. Offsets below are relative to this.
_NOW = datetime.now(UTC)
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


def _posting(
    engine: Engine,
    employer_id: int,
    title: str,
    *,
    first_seen: datetime = _NOW,
    comp_min: int | None = None,
    comp_max: int | None = None,
    comp_raw: str | None = None,
    description: str | None = None,
    location: str | None = None,
    in_scope: bool = True,
) -> int:
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
                in_scope=in_scope,
                description=description,
                location=location,
                comp_min=comp_min,
                comp_max=comp_max,
                comp_raw=comp_raw,
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


def _match(
    engine: Engine,
    posting_id: int,
    profile: Profile,
    *,
    verdict: str = "yes",
    advice: dict[str, str] | None = None,
) -> None:
    with begin(engine) as conn:
        save_match(
            conn,
            posting_id,
            profile.id,
            profile.resume_version,
            {
                "verdict": verdict,
                "score": 70,
                "fits": "[]",
                "gaps": "[]",
                "rationale": "ok",
                **(advice or {}),
            },
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


def test_verticals_lists_configured(migrated_engine: Engine) -> None:
    """The picker lists CONFIGURED verticals (config-driven), not ones that already have a profile —
    so a vertical stays joinable with zero profiles in it (the B-4 chicken-and-egg fix, D-064)."""
    got = _client(migrated_engine).get("/api/verticals").json()
    assert set(got) == {
        "grid_power_software",
        "aviation_software",
        "robotics_software",
        "trading_software",
    }


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


def test_compensation_fields_and_guarded_display(migrated_engine: Engine) -> None:
    """`comp_display` is the server's judgment, not the SPA's (F2 Phase A, D-087): an annual-USD
    posting gets a formatted range, an hourly-annualized one gets `null` while `comp_raw` still
    ships so the SPA can show the posting's own wording."""
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    annual = _posting(
        migrated_engine,
        emp,
        "annual",
        comp_min=105_000,
        comp_max=131_325,
        comp_raw="$105,000 and $131,325/year",
    )
    hourly = _posting(
        migrated_engine,
        emp,
        "hourly",
        comp_min=103_579,
        comp_max=125_258,
        comp_raw="$49.82 to $60.22 per hour",
    )
    none_stated = _posting(migrated_engine, emp, "none_stated")
    for posting_id in (annual, hourly, none_stated):
        _match(migrated_engine, posting_id, prof)

    body = _client(migrated_engine).get("/api/postings", params={"vertical": _VERTICAL}).json()
    rows = {p["title"]: p for p in body["postings"]}

    assert rows["annual"]["comp_display"] == "$105,000 – $131,325"
    assert rows["annual"]["comp_raw"] == "$105,000 and $131,325/year"
    assert rows["annual"]["comp_min"] == 105_000

    # The fabrication guard: integers still ship, but nothing formats them into a salary.
    assert rows["hourly"]["comp_display"] is None
    assert rows["hourly"]["comp_raw"] == "$49.82 to $60.22 per hour"

    assert rows["none_stated"]["comp_display"] is None
    assert rows["none_stated"]["comp_raw"] is None


def test_location_display_is_served_beside_the_raw_location(migrated_engine: Engine) -> None:
    """`location_display` is the server's normalization (D-106) and `location` stays the raw
    L1-authoritative string (D-043); an already-clean location gets `null` so the SPA falls back."""
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    for title, location in (
        ("messy", "USA - Seal Beach, CA"),
        ("clean", "Olathe, Kansas"),
        ("nowhere", None),
    ):
        _match(migrated_engine, _posting(migrated_engine, emp, title, location=location), prof)

    body = _client(migrated_engine).get("/api/postings", params={"vertical": _VERTICAL}).json()
    rows = {p["title"]: p for p in body["postings"]}

    assert rows["messy"]["location"] == "USA - Seal Beach, CA"  # stored value is untouched
    assert rows["messy"]["location_display"] == "Seal Beach, California"
    assert rows["clean"]["location_display"] is None
    assert rows["nowhere"]["location_display"] is None


def test_match_advice_is_served_to_the_authenticated_row(migrated_engine: Engine) -> None:
    """The D-111 advice reaches a logged-in reader, parsed back into real lists.

    The three cases are the three storage states, and they are not interchangeable: a row with
    advice, a row the model declined to advise on (`"[]"`), and a row matched before the columns
    existed (NULL). Only the first renders anything; the other two must both arrive as `null` so
    the panel has one absence to handle rather than two.
    """
    prof = _profile(migrated_engine)
    emp = _employer(migrated_engine)
    _match(
        migrated_engine,
        _posting(migrated_engine, emp, "advised"),
        prof,
        advice={
            "resume_actions": '["Lead with the dispatch simulator"]',
            "application_notes": '["Name the missing production experience"]',
        },
    )
    _match(
        migrated_engine,
        _posting(migrated_engine, emp, "declined"),
        prof,
        advice={"resume_actions": "[]", "application_notes": "[]"},
    )
    _match(migrated_engine, _posting(migrated_engine, emp, "legacy"), prof)

    body = _client(migrated_engine).get("/api/postings", params={"vertical": _VERTICAL}).json()
    rows = {p["title"]: p for p in body["postings"]}

    assert rows["advised"]["resume_actions"] == ["Lead with the dispatch simulator"]
    assert rows["advised"]["application_notes"] == ["Name the missing production experience"]
    # Declined and legacy are indistinguishable to the reader, by design.
    assert rows["declined"]["resume_actions"] is None
    assert rows["declined"]["application_notes"] is None
    assert rows["legacy"]["resume_actions"] is None
    assert rows["legacy"]["application_notes"] is None


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
    old = _posting(migrated_engine, emp, "old", first_seen=_NOW - timedelta(days=5))
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


# --- authz (Phase 9.2, D-055) ----------------------------------------------------------------
# The read path resolves the profile from the authenticated user (docs/11 §2 seam). We inject the
# user via a dependency override rather than the full OAuth dance (that's pinned in test_auth.py).


def _authed_client(engine: Engine, email: str) -> TestClient:
    app = create_app(engine)
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, google_sub="g-1", email=email, name=None
    )
    return TestClient(app)


def test_authed_user_resolves_own_profile(migrated_engine: Engine) -> None:
    """With two profiles present, an authed user resolves to *their own* without a profile_id —
    no 409. (Contrast test_409_when_multiple_active_profiles on the unauthenticated path.)"""
    mine = _profile(migrated_engine, email="me@example.com")
    _profile(migrated_engine, email="other@example.com")
    emp = _employer(migrated_engine)
    matched = _posting(migrated_engine, emp, "mine")
    _match(migrated_engine, matched, mine)

    resp = _authed_client(migrated_engine, "me@example.com").get(
        "/api/postings", params={"vertical": _VERTICAL}
    )
    assert resp.status_code == 200
    assert resp.json()["profile_id"] == mine.id
    assert _titles(resp.json()) == ["mine"]


def test_authed_user_forbidden_anothers_profile_id(migrated_engine: Engine) -> None:
    mine = _profile(migrated_engine, email="me@example.com")
    other = _profile(migrated_engine, email="other@example.com")
    resp = _authed_client(migrated_engine, "me@example.com").get(
        "/api/postings", params={"vertical": _VERTICAL, "profile_id": other.id}
    )
    assert resp.status_code == 403
    assert mine  # (the user does have their own profile; the 403 is about ownership, not existence)


def test_auth_required_blocks_anonymous(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The enforcement seam: with VJA_AUTH_REQUIRED on, an unauthenticated read is 401."""
    monkeypatch.setenv("VJA_AUTH_REQUIRED", "1")
    _profile(migrated_engine)
    resp = _client(migrated_engine).get("/api/postings", params={"vertical": _VERTICAL})
    assert resp.status_code == 401


# --- résumé upload + signup backfill (Phase 9.3, D-057) --------------------------------------
# The first write endpoint. require_user is overridden (the OAuth dance is pinned in test_auth.py)
# and run_backfill is patched out so the BackgroundTask doesn't reach the real provider client
# (TestClient runs background tasks synchronously after the response).

_TEXT_FILE = {"file": ("resume.txt", b"Jane Engineer. Python, grid software.", "text/plain")}


def _user(engine: Engine, email: str = "me@example.com") -> User:
    return upsert_user_by_google(engine, google_sub=f"g-{email}", email=email, name="Me")


def _upload_client(
    engine: Engine, user: User, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, list[tuple[tuple, dict]]]:  # type: ignore[type-arg]
    """An authed client with run_backfill stubbed; returns the client + a log of backfill calls."""
    calls: list[tuple[tuple, dict]] = []  # type: ignore[type-arg]
    monkeypatch.setattr("vja.api.app.run_backfill", lambda *a, **k: calls.append((a, k)))
    app = create_app(engine)
    app.dependency_overrides[require_user] = lambda: user
    return TestClient(app), calls


def test_upload_requires_auth(migrated_engine: Engine) -> None:
    resp = _client(migrated_engine).post(
        "/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE
    )
    assert resp.status_code == 401


def test_upload_creates_profile_links_user_and_triggers_backfill(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(migrated_engine)
    client, calls = _upload_client(migrated_engine, user, monkeypatch)

    resp = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE)
    assert resp.status_code == 202
    body = resp.json()
    assert body["vertical"] == _VERTICAL

    pid = body["profile_id"]
    prof = get_profile(migrated_engine, pid)
    assert prof is not None
    assert prof.user_email == user.email
    assert body["resume_version"] == prof.resume_version

    # user_id stamped at creation (the D-055 link, here at upload not just login).
    with migrated_engine.connect() as conn:
        uid = conn.execute(select(profiles.c.user_id).where(profiles.c.id == pid)).scalar_one()
    assert uid == user.id

    # backfill kicked off for exactly this profile/vertical.
    assert len(calls) == 1
    args, _kwargs = calls[0]
    assert args[1] == _VERTICAL
    assert args[2].id == pid


def test_upload_rejects_unreadable_file(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, calls = _upload_client(migrated_engine, _user(migrated_engine), monkeypatch)
    resp = client.post(
        "/api/profiles",
        data={"vertical": _VERTICAL},
        files={"file": ("resume.txt", b"\xff\xfe\x00garbage", "text/plain")},
    )
    assert resp.status_code == 422
    assert calls == []  # never reached the backfill


def test_upload_unknown_vertical_404(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, calls = _upload_client(migrated_engine, _user(migrated_engine), monkeypatch)
    resp = client.post("/api/profiles", data={"vertical": "no_such_vertical"}, files=_TEXT_FILE)
    assert resp.status_code == 404
    assert calls == []


def test_upload_refused_over_daily_budget_429(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VJA_DAILY_LLM_BUDGET_USD", "0")
    client, calls = _upload_client(migrated_engine, _user(migrated_engine), monkeypatch)
    resp = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE)
    assert resp.status_code == 429
    assert calls == []


def test_upload_oversize_413(migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vja.api.app._MAX_UPLOAD_BYTES", 8)
    client, calls = _upload_client(migrated_engine, _user(migrated_engine), monkeypatch)
    resp = client.post(
        "/api/profiles",
        data={"vertical": _VERTICAL},
        files={"file": ("resume.txt", b"way more than eight bytes", "text/plain")},
    )
    assert resp.status_code == 413
    assert calls == []


# --- pasted résumé text (Update 1.2, PR 1) -----------------------------------------------------
# The endpoint takes exactly one of `file` / `resume_text`. Everything after the D-033 adapter is
# shared code, so these tests exist to prove the paste path reaches it *and* that no guard was
# weakened on the way past: identical-content no-op, rolling reupload clock, daily ceiling, and
# the one-vertical 409 all key on the extracted text and must behave identically.

_PASTED = "Jane Engineer. Python, grid software."


def test_paste_creates_profile_and_triggers_backfill(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(migrated_engine)
    client, calls = _upload_client(migrated_engine, user, monkeypatch)

    resp = client.post(
        "/api/profiles", data={"vertical": _VERTICAL, "resume_text": f"  {_PASTED}  "}
    )
    assert resp.status_code == 202

    prof = get_profile(migrated_engine, resp.json()["profile_id"])
    assert prof is not None
    assert prof.resume_text == _PASTED  # stripped by the adapter, stored verbatim otherwise
    assert prof.user_email == user.email
    assert len(calls) == 1


def test_paste_and_file_together_is_422(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A client sending both has a bug; silently picking one would hide it."""
    client, calls = _upload_client(migrated_engine, _user(migrated_engine), monkeypatch)
    resp = client.post(
        "/api/profiles",
        data={"vertical": _VERTICAL, "resume_text": _PASTED},
        files=_TEXT_FILE,
    )
    assert resp.status_code == 422
    assert "not both" in resp.json()["detail"]
    assert calls == []


def test_neither_file_nor_text_is_422(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, calls = _upload_client(migrated_engine, _user(migrated_engine), monkeypatch)
    resp = client.post("/api/profiles", data={"vertical": _VERTICAL})
    assert resp.status_code == 422
    assert calls == []


@pytest.mark.parametrize("pasted", ["", "   \n\t "])
def test_paste_without_usable_text_is_422(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch, pasted: str
) -> None:
    client, calls = _upload_client(migrated_engine, _user(migrated_engine), monkeypatch)
    resp = client.post("/api/profiles", data={"vertical": _VERTICAL, "resume_text": pasted})
    assert resp.status_code == 422
    assert calls == []


def test_paste_over_the_character_cap_is_422(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, calls = _upload_client(migrated_engine, _user(migrated_engine), monkeypatch)
    resp = client.post(
        "/api/profiles",
        data={"vertical": _VERTICAL, "resume_text": "a" * (_MAX_RESUME_CHARS + 1)},
    )
    assert resp.status_code == 422
    assert "too long" in resp.json()["detail"]
    assert calls == []


def test_paste_of_identical_content_is_the_same_no_op_as_a_file_reupload(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-085 keys on the extracted text, not the transport: pasting what was uploaded changes
    nothing and schedules nothing."""
    user = _user(migrated_engine)
    client, calls = _upload_client(migrated_engine, user, monkeypatch)

    uploaded = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE)
    assert uploaded.status_code == 202

    pasted = client.post("/api/profiles", data={"vertical": _VERTICAL, "resume_text": _PASTED})
    assert pasted.status_code == 202
    assert pasted.json() == uploaded.json()  # same profile, same resume_version
    assert len(calls) == 1  # no second backfill


def test_paste_is_held_to_the_rolling_reupload_limit(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(migrated_engine)
    client, calls = _upload_client(migrated_engine, user, monkeypatch)

    with freeze_time("2026-07-15 12:00:00"):
        first = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE)
        assert first.status_code == 202
        changed = client.post(
            "/api/profiles", data={"vertical": _VERTICAL, "resume_text": f"{_PASTED} SCADA."}
        )
        assert changed.status_code == 202

        blocked = client.post(
            "/api/profiles", data={"vertical": _VERTICAL, "resume_text": f"{_PASTED} SCADA, EMS."}
        )
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"] == "86400"

    assert len(calls) == 2


def test_paste_refused_over_daily_budget_429(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VJA_DAILY_LLM_BUDGET_USD", "0")
    client, calls = _upload_client(migrated_engine, _user(migrated_engine), monkeypatch)
    resp = client.post("/api/profiles", data={"vertical": _VERTICAL, "resume_text": _PASTED})
    assert resp.status_code == 429
    assert calls == []


def test_paste_into_a_second_vertical_rejected_409(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-104: the résumé form never moves a vertical, whichever input mode it used."""
    user = _user(migrated_engine)
    _profile(migrated_engine, email=user.email)  # active grid profile
    client, calls = _upload_client(migrated_engine, user, monkeypatch)

    resp = client.post(
        "/api/profiles", data={"vertical": "aviation_software", "resume_text": _PASTED}
    )
    assert resp.status_code == 409
    assert "one vertical per user" in resp.json()["detail"]
    assert calls == []


def test_paste_unknown_vertical_404(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, calls = _upload_client(migrated_engine, _user(migrated_engine), monkeypatch)
    resp = client.post(
        "/api/profiles", data={"vertical": "no_such_vertical", "resume_text": _PASTED}
    )
    assert resp.status_code == 404
    assert calls == []


def test_paste_requires_auth(migrated_engine: Engine) -> None:
    resp = _client(migrated_engine).post(
        "/api/profiles", data={"vertical": _VERTICAL, "resume_text": _PASTED}
    )
    assert resp.status_code == 401


def test_paste_stamps_started_before_scheduling(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The D-082 commit-point guarantee is transport-independent: the SPA's immediate post-202
    /api/me probe sees `running` after a paste too."""
    user = _user(migrated_engine)
    client, _calls = _upload_client(migrated_engine, user, monkeypatch)
    resp = client.post("/api/profiles", data={"vertical": _VERTICAL, "resume_text": _PASTED})
    assert resp.status_code == 202

    started, completed = backfill_stamps(migrated_engine, resp.json()["profile_id"])
    assert started is not None
    assert completed is None
    me = _authed_client(migrated_engine, user.email).get("/api/me")
    assert me.json()["profile"]["backfill_status"] == "running"


# --- /api/me: the SPA's routing source of truth (Phase B, D-064/D-065) ------------------------
# /api/me now returns {user, profile|null} so the SPA routes to *this user's* vertical instead of a
# global picker. get_current_user is injected via Depends, so _authed_client's override applies.


def test_me_returns_user_and_profile(migrated_engine: Engine) -> None:
    """Authed + onboarded → the user + their one vertical/resume_version (the SPA routes on it)."""
    mine = _profile(migrated_engine, email="me@example.com")
    resp = _authed_client(migrated_engine, "me@example.com").get("/api/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "me@example.com"
    assert body["profile"] == {
        "vertical": _VERTICAL,
        "resume_version": mine.resume_version,
        "backfill_status": None,  # seeded profile, never stamped (D-082)
    }


def test_me_profile_null_when_not_onboarded(migrated_engine: Engine) -> None:
    """Authed but no profile yet → profile is null (⇒ SPA sends them to onboarding, not a 404)."""
    resp = _authed_client(migrated_engine, "newuser@example.com").get("/api/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "newuser@example.com"
    assert body["profile"] is None


# --- one-vertical-per-user enforcement at the write path (Phase B, D-064) ----------------------


def test_upload_second_vertical_rejected_409(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user already onboarded to grid uploading an aviation résumé → 409; backfill never runs."""
    user = _user(migrated_engine)
    _profile(migrated_engine, email=user.email)  # active grid profile
    client, calls = _upload_client(migrated_engine, user, monkeypatch)

    resp = client.post("/api/profiles", data={"vertical": "aviation_software"}, files=_TEXT_FILE)
    assert resp.status_code == 409
    assert "one vertical per user" in resp.json()["detail"]
    assert calls == []


def test_reupload_same_vertical_updates_resume(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-upload of the SAME vertical is an idempotent résumé update → 202 + new resume_version."""
    user = _user(migrated_engine)
    original = _profile(migrated_engine, email=user.email)
    client, calls = _upload_client(migrated_engine, user, monkeypatch)

    resp = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE)
    assert resp.status_code == 202
    body = resp.json()
    assert body["vertical"] == _VERTICAL
    assert body["resume_version"] != original.resume_version  # résumé text changed → new version
    assert len(calls) == 1  # backfill runs for the update


@freeze_time("2026-07-15 12:00:00")
def test_reupload_via_api_versions_and_enforces_rolling_cooldown(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-085: identical content is a no-backfill success; only one changed reupload may start
    a backfill per user in a rolling 24-hour window."""
    user = _user(migrated_engine)
    client, calls = _upload_client(migrated_engine, user, monkeypatch)

    first_response = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE)
    assert first_response.status_code == 202
    first = first_response.json()
    first_started = backfill_stamps(migrated_engine, first["profile_id"])[0]
    assert first_started is not None
    with migrated_engine.connect() as conn:
        first_clock = conn.execute(
            select(users.c.last_resume_reupload_at).where(users.c.id == user.id)
        ).scalar_one()
    assert first_clock is None  # the initial upload never consumes the reupload allowance

    # Identical extracted content returns the unchanged 202 contract but spends nothing: no new
    # task and no fresh progress stamp. It therefore also succeeds when the global LLM ceiling is
    # exhausted (that ceiling only guards work that would actually run).
    monkeypatch.setenv("VJA_DAILY_LLM_BUDGET_USD", "0")
    same = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE)
    assert same.status_code == 202
    assert same.json() == first
    assert len(calls) == 1
    assert backfill_stamps(migrated_engine, first["profile_id"])[0] == first_started
    monkeypatch.delenv("VJA_DAILY_LLM_BUDGET_USD")

    # The first changed reupload is allowed and starts one new backfill.
    edited = {"file": ("resume.txt", b"Jane Engineer. Python, grid software, SCADA.", "text/plain")}
    resp = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=edited)
    assert resp.status_code == 202
    body = resp.json()
    assert body["resume_version"] != first["resume_version"]
    assert body["profile_id"] != first["profile_id"]
    with migrated_engine.connect() as conn:
        claimed_at = conn.execute(
            select(users.c.last_resume_reupload_at).where(users.c.id == user.id)
        ).scalar_one()
    assert claimed_at == datetime(2026, 7, 15, 12, 0, tzinfo=UTC)

    # A second changed reupload in the same rolling window is blocked before profile mutation or
    # task scheduling, and tells the client exactly when it may retry.
    second_edit = {
        "file": ("resume.txt", b"Jane Engineer. Python, grid software, SCADA, EMS.", "text/plain")
    }
    blocked = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=second_edit)
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "86400"
    assert "one per user every 24 hours" in blocked.json()["detail"]

    # exactly one active profile survives: the new version (the old one is deactivated, D-064).
    assert [p.id for p in active_profiles(migrated_engine, _VERTICAL)] == [body["profile_id"]]

    # Only the initial upload and accepted changed reupload kicked off a backfill.
    assert [args[2].id for args, _ in calls] == [
        first["profile_id"],
        body["profile_id"],
    ]


def test_changed_reupload_allowed_at_rolling_window_boundary(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(migrated_engine)
    client, calls = _upload_client(migrated_engine, user, monkeypatch)

    with freeze_time("2026-07-14 12:00:00"):
        first = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE)
        assert first.status_code == 202
        edit = {
            "file": ("resume.txt", b"Jane Engineer. Python, grid software, SCADA.", "text/plain")
        }
        assert (
            client.post("/api/profiles", data={"vertical": _VERTICAL}, files=edit).status_code
            == 202
        )

    with freeze_time("2026-07-15 11:59:59"):
        too_soon = {
            "file": (
                "resume.txt",
                b"Jane Engineer. Python, grid software, SCADA, EMS.",
                "text/plain",
            )
        }
        blocked = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=too_soon)
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"] == "1"

    with freeze_time("2026-07-15 12:00:00"):
        allowed = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=too_soon)
        assert allowed.status_code == 202

    assert len(calls) == 3


def test_reverting_to_inactive_resume_counts_as_changed_reupload(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reusing an old content hash reactivates its audit row, but still advances the user clock."""
    user = _user(migrated_engine)
    client, calls = _upload_client(migrated_engine, user, monkeypatch)

    with freeze_time("2026-07-14 12:00:00"):
        original = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE)
        assert original.status_code == 202
        edited = {
            "file": ("resume.txt", b"Jane Engineer. Python, grid software, SCADA.", "text/plain")
        }
        assert (
            client.post("/api/profiles", data={"vertical": _VERTICAL}, files=edited).status_code
            == 202
        )

    with freeze_time("2026-07-15 12:00:00"):
        reverted = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE)
        assert reverted.status_code == 202
        assert reverted.json()["profile_id"] == original.json()["profile_id"]

    with freeze_time("2026-07-15 12:00:01"):
        another_edit = {
            "file": ("resume.txt", b"Jane Engineer. Python, grid software, EMS.", "text/plain")
        }
        blocked = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=another_edit)
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"] == "86399"

    assert len(calls) == 3


@freeze_time("2026-07-15 12:00:00")
def test_reupload_cooldown_is_per_user(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_user = _user(migrated_engine, "first@example.com")
    second_user = _user(migrated_engine, "second@example.com")
    first_client, first_calls = _upload_client(migrated_engine, first_user, monkeypatch)

    assert (
        first_client.post(
            "/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE
        ).status_code
        == 202
    )
    first_edit = {"file": ("resume.txt", b"First user changed resume.", "text/plain")}
    assert (
        first_client.post(
            "/api/profiles", data={"vertical": _VERTICAL}, files=first_edit
        ).status_code
        == 202
    )

    second_client, second_calls = _upload_client(migrated_engine, second_user, monkeypatch)
    assert (
        second_client.post(
            "/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE
        ).status_code
        == 202
    )
    second_edit = {"file": ("resume.txt", b"Second user changed resume.", "text/plain")}
    assert (
        second_client.post(
            "/api/profiles", data={"vertical": _VERTICAL}, files=second_edit
        ).status_code
        == 202
    )

    assert len(first_calls) == 2
    assert len(second_calls) == 2


# --- backfill status via /api/me (D-082) -------------------------------------------------------
# Derivation logic is unit-pinned in test_profiles.py; here we pin the HTTP surface: the upload
# endpoint stamps `started` BEFORE scheduling the background task (so the SPA's immediate post-202
# /api/me probe sees `running`), and /api/me exposes the derived status per state.


def test_upload_stamps_started_and_me_reports_running(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With run_backfill stubbed out (it never completes), the endpoint's own pre-schedule stamp
    must already make /api/me say running — the no-race guarantee the SPA banner rests on."""
    user = _user(migrated_engine)
    client, _calls = _upload_client(migrated_engine, user, monkeypatch)
    resp = client.post("/api/profiles", data={"vertical": _VERTICAL}, files=_TEXT_FILE)
    assert resp.status_code == 202
    pid = resp.json()["profile_id"]

    started, completed = backfill_stamps(migrated_engine, pid)
    assert started is not None
    assert completed is None

    me = _authed_client(migrated_engine, user.email).get("/api/me")
    assert me.status_code == 200
    assert me.json()["profile"]["backfill_status"] == "running"


def test_me_reports_done_after_completion_stamp(migrated_engine: Engine) -> None:
    prof = _profile(migrated_engine, email="me@example.com")
    mark_backfill_started(migrated_engine, prof.id)
    mark_backfill_completed(migrated_engine, prof.id)
    body = _authed_client(migrated_engine, "me@example.com").get("/api/me").json()
    assert body["profile"]["backfill_status"] == "done"


def test_me_backfill_status_null_for_unstamped_profile(migrated_engine: Engine) -> None:
    """Pre-D-082 rows (e.g. the seeded profile) carry no stamps → status is null, not an error."""
    _profile(migrated_engine, email="me@example.com")
    body = _authed_client(migrated_engine, "me@example.com").get("/api/me").json()
    assert body["profile"]["backfill_status"] is None


# --- posting body: GET /api/postings/{id} (D-095 PR 2) -----------------------------------------
# Its own endpoint so ~3 KB bodies stay off the list response; same visibility gate as the list.


def test_posting_detail_returns_the_stored_body(migrated_engine: Engine) -> None:
    _profile(migrated_engine)
    employer_id = _employer(migrated_engine)
    posting_id = _posting(migrated_engine, employer_id, "swe", description="About the role\n\nGo.")

    resp = _client(migrated_engine).get(
        f"/api/postings/{posting_id}", params={"vertical": _VERTICAL}
    )

    assert resp.status_code == 200
    assert resp.json() == {"posting_id": posting_id, "description": "About the role\n\nGo."}


def test_posting_detail_returns_null_for_a_row_with_no_body_yet(migrated_engine: Engine) -> None:
    # The no-backfill state (D-095): a real posting, no body captured yet. Not an error.
    _profile(migrated_engine)
    posting_id = _posting(migrated_engine, _employer(migrated_engine), "swe")

    resp = _client(migrated_engine).get(
        f"/api/postings/{posting_id}", params={"vertical": _VERTICAL}
    )

    assert resp.status_code == 200
    assert resp.json()["description"] is None


def test_posting_detail_404s_an_unknown_id(migrated_engine: Engine) -> None:
    _profile(migrated_engine)
    resp = _client(migrated_engine).get("/api/postings/999", params={"vertical": _VERTICAL})
    assert resp.status_code == 404


def test_posting_detail_404s_an_id_from_another_vertical(migrated_engine: Engine) -> None:
    # Enumerating ids must not read across verticals — the query is floored on the caller's own.
    _profile(migrated_engine)
    other = _employer(migrated_engine, vertical="aviation_software", name="AirCo")
    posting_id = _posting(migrated_engine, other, "avia-swe", description="Другой vertical.")

    resp = _client(migrated_engine).get(
        f"/api/postings/{posting_id}", params={"vertical": _VERTICAL}
    )

    assert resp.status_code == 404


def test_posting_detail_404s_an_out_of_scope_posting(migrated_engine: Engine) -> None:
    # The dashboard universe is the in-scope set (D-043); the body endpoint uses the same floor.
    _profile(migrated_engine)
    posting_id = _posting(
        migrated_engine, _employer(migrated_engine), "ops", description="x", in_scope=False
    )

    resp = _client(migrated_engine).get(
        f"/api/postings/{posting_id}", params={"vertical": _VERTICAL}
    )

    assert resp.status_code == 404


def test_posting_detail_requires_auth_when_enforced(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VJA_AUTH_REQUIRED", "1")
    _profile(migrated_engine)
    posting_id = _posting(migrated_engine, _employer(migrated_engine), "swe", description="Body.")

    resp = _client(migrated_engine).get(
        f"/api/postings/{posting_id}", params={"vertical": _VERTICAL}
    )

    assert resp.status_code == 401


def test_list_response_still_carries_no_body(migrated_engine: Engine) -> None:
    # The whole point of the separate endpoint: a dashboard load must not ship descriptions.
    _profile(migrated_engine)
    _posting(migrated_engine, _employer(migrated_engine), "swe", description="A long body.")

    body = (
        _client(migrated_engine)
        .get("/api/postings", params={"vertical": _VERTICAL, "view": "cleaned"})
        .json()
    )

    assert body["count"] == 1
    assert "description" not in body["postings"][0]
