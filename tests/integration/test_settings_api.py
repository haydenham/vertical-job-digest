"""Integration tests for the settings surface (D-094 PR 3) — `PATCH /api/me` + `DELETE /api/me`.

The digest pause/resume toggle reuses the unsubscribe path's `set_digest_paused`; hard account
deletion removes every user-scoped row (user → profiles → matches → digest rows) in one
transaction and never touches the shared corpus (postings/employers — D-009 covers postings, not
user PII). Auth is injected via dependency override (the real-session flow, including the
delete-kills-the-session behavior, is pinned in `test_auth.py`).
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import ColumnElement, Engine, Table, func, select

from vja.api.app import create_app
from vja.api.auth import get_current_user, require_user
from vja.db.digests import create_pending
from vja.db.engine import begin
from vja.db.matches import save_match
from vja.db.profiles import Profile, active_profile_for_user, active_profiles, upsert_profile
from vja.db.schema import digests, employers, matches, postings, profiles, users
from vja.db.users import User, upsert_user_by_google

_NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
_VERTICAL = "grid_power_software"
_EMAIL = "me@example.com"


def _user(engine: Engine, email: str = _EMAIL) -> User:
    return upsert_user_by_google(engine, google_sub=f"g-{email}", email=email, name="Me")


def _profile(engine: Engine, *, email: str = _EMAIL) -> Profile:
    upsert_profile(
        engine, user_email=email, vertical=_VERTICAL, resume_text=email, domain_vocabulary=[]
    )
    return next(p for p in active_profiles(engine, _VERTICAL) if p.user_email == email)


def _employer(engine: Engine, name: str = "GridCo") -> int:
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical=_VERTICAL,
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


def _posting(engine: Engine, employer_id: int, title: str) -> int:
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
                first_seen_at=_NOW,
                last_seen_at=_NOW,
                extracted_at=_NOW,
                in_scope=True,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _match(engine: Engine, posting_id: int, profile: Profile) -> None:
    with begin(engine) as conn:
        save_match(
            conn,
            posting_id,
            profile.id,
            profile.resume_version,
            {"verdict": "yes", "score": 70, "fits": "[]", "gaps": "[]", "rationale": "ok"},
            model="test-model",
            trigger="nightly",
            now=_NOW,
        )


def _digest(engine: Engine, recipient: str) -> None:
    with begin(engine) as conn:
        create_pending(conn, recipient=recipient, vertical=_VERTICAL, contents={})


def _client(engine: Engine, user: User | None = None) -> TestClient:
    """Anonymous client, or one authed as `user` (both auth dependencies overridden — require_user
    calls get_current_user directly, so each needs its own override)."""
    app = create_app(engine)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[require_user] = lambda: user
    return TestClient(app)


def _count(engine: Engine, table: Table, *where: ColumnElement[bool]) -> int:
    stmt = select(func.count()).select_from(table)
    for clause in where:
        stmt = stmt.where(clause)
    with engine.connect() as conn:
        return int(conn.execute(stmt).scalar_one())


def _paused(engine: Engine, user_id: int) -> bool:
    with engine.connect() as conn:
        return bool(
            conn.execute(select(users.c.digest_paused).where(users.c.id == user_id)).scalar_one()
        )


# --- digest_paused in /api/me + PATCH toggle --------------------------------------------------


def test_me_exposes_digest_paused(migrated_engine: Engine) -> None:
    user = _user(migrated_engine)
    body = _client(migrated_engine, user).get("/api/me").json()
    assert body["user"]["digest_paused"] is False


def test_patch_pauses_then_resumes(migrated_engine: Engine) -> None:
    user = _user(migrated_engine)
    client = _client(migrated_engine, user)

    resp = client.patch("/api/me", json={"digest_paused": True})
    assert resp.status_code == 200
    # The response echoes the full settings state, not just the patched field — `vertical` is
    # None here because this user has no profile.
    assert resp.json() == {"digest_paused": True, "vertical": None}
    assert _paused(migrated_engine, user.id)

    # /api/me reflects the flip (fresh client — the override captures a stale dataclass).
    fresh = upsert_user_by_google(migrated_engine, google_sub=f"g-{_EMAIL}", email=_EMAIL)
    assert _client(migrated_engine, fresh).get("/api/me").json()["user"]["digest_paused"] is True

    resp = client.patch("/api/me", json={"digest_paused": False})
    assert resp.status_code == 200
    assert not _paused(migrated_engine, user.id)


def test_patch_is_idempotent(migrated_engine: Engine) -> None:
    user = _user(migrated_engine)
    client = _client(migrated_engine, user)
    for _ in range(2):
        assert client.patch("/api/me", json={"digest_paused": True}).status_code == 200
    assert _paused(migrated_engine, user.id)


def test_patch_requires_auth(migrated_engine: Engine) -> None:
    resp = _client(migrated_engine).patch("/api/me", json={"digest_paused": True})
    assert resp.status_code == 401


def test_patch_404_when_user_row_vanished(migrated_engine: Engine) -> None:
    """A concurrently deleted account: the override still authenticates, but no row updates."""
    ghost = User(id=99999, google_sub="g-ghost", email="ghost@example.com", name=None)
    resp = _client(migrated_engine, ghost).patch("/api/me", json={"digest_paused": True})
    assert resp.status_code == 404


# --- hard account deletion --------------------------------------------------------------------


def test_delete_requires_auth(migrated_engine: Engine) -> None:
    assert _client(migrated_engine).delete("/api/me").status_code == 401


def test_delete_removes_user_scoped_rows_and_preserves_corpus(migrated_engine: Engine) -> None:
    """DELETE /api/me removes the user + their profile/matches/digests; postings/employers and
    every other-user row survive (isolation)."""
    emp = _employer(migrated_engine)
    p1 = _posting(migrated_engine, emp, "role-1")
    p2 = _posting(migrated_engine, emp, "role-2")

    mine_profile = _profile(migrated_engine, email=_EMAIL)  # created pre-login → user_id NULL
    mine = _user(migrated_engine)  # login links it (D-055)
    _match(migrated_engine, p1, mine_profile)
    _digest(migrated_engine, _EMAIL)

    other_profile = _profile(migrated_engine, email="other@example.com")
    other = _user(migrated_engine, email="other@example.com")
    _match(migrated_engine, p2, other_profile)
    _digest(migrated_engine, "other@example.com")

    resp = _client(migrated_engine, mine).delete("/api/me")
    assert resp.status_code == 204

    e = migrated_engine
    assert _count(e, users, users.c.id == mine.id) == 0
    assert _count(e, profiles, profiles.c.user_email == _EMAIL) == 0
    assert _count(e, matches, matches.c.profile_id == mine_profile.id) == 0
    assert _count(e, digests, digests.c.recipient == _EMAIL) == 0

    # The other user's account is untouched.
    assert _count(e, users, users.c.id == other.id) == 1
    assert _count(e, profiles, profiles.c.id == other_profile.id) == 1
    assert _count(e, matches, matches.c.profile_id == other_profile.id) == 1
    assert _count(e, digests, digests.c.recipient == "other@example.com") == 1

    # Shared corpus survives (D-009 covers postings; deletion is user PII only).
    assert _count(e, postings) == 2
    assert _count(e, employers) == 1


def test_delete_reaches_unlinked_seed_profile(migrated_engine: Engine) -> None:
    """A pre-login profile row (user_id NULL, email-keyed) and its matches go too — the
    `user_id OR user_email` predicate (D-055 seam)."""
    emp = _employer(migrated_engine)
    posting = _posting(migrated_engine, emp, "role-1")

    user = _user(migrated_engine)  # user exists first…
    seed = _profile(migrated_engine, email=_EMAIL)  # …so this profile is never linked
    _match(migrated_engine, posting, seed)

    with migrated_engine.connect() as conn:
        assert (
            conn.execute(select(profiles.c.user_id).where(profiles.c.id == seed.id)).scalar_one()
            is None
        )

    assert _client(migrated_engine, user).delete("/api/me").status_code == 204
    assert _count(migrated_engine, profiles, profiles.c.id == seed.id) == 0
    assert _count(migrated_engine, matches, matches.c.profile_id == seed.id) == 0


def test_delete_without_profile(migrated_engine: Engine) -> None:
    """A signed-in but never-onboarded user can still delete their account (D-094)."""
    user = _user(migrated_engine)
    assert _client(migrated_engine, user).delete("/api/me").status_code == 204
    assert _count(migrated_engine, users, users.c.id == user.id) == 0


# --- vertical switching over PATCH /api/me ------------------------------------------------------
# The self-serve replacement for what D-064 made a support action. run_backfill is stubbed so the
# BackgroundTask never reaches a real provider (TestClient runs them synchronously after the
# response); the DB-level cost model is pinned in test_profiles.py.

_OTHER = "aviation_software"


def _switch_client(
    engine: Engine, user: User, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, list[tuple[tuple, dict]]]:  # type: ignore[type-arg]
    calls: list[tuple[tuple, dict]] = []  # type: ignore[type-arg]
    monkeypatch.setattr("vja.api.app.run_backfill", lambda *a, **k: calls.append((a, k)))
    app = create_app(engine)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_user] = lambda: user
    return TestClient(app), calls


def _set_switch_clock(engine: Engine, user_id: int, when: datetime) -> None:
    with begin(engine) as conn:
        conn.execute(
            users.update().where(users.c.id == user_id).values(last_vertical_switch_at=when)
        )


def test_patch_switches_vertical_and_schedules_backfill(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(migrated_engine)
    _profile(migrated_engine)
    client, calls = _switch_client(migrated_engine, user, monkeypatch)

    resp = client.patch("/api/me", json={"vertical": _OTHER})

    assert resp.status_code == 200
    assert resp.json() == {"digest_paused": False, "vertical": _OTHER}
    active = active_profile_for_user(migrated_engine, _EMAIL)
    assert active is not None and active.vertical == _OTHER
    # The résumé rode across untouched — a switch is never a re-upload.
    assert active.resume_text == _EMAIL
    assert len(calls) == 1
    assert calls[0][0][1] == _OTHER


def test_patch_switch_rejects_unknown_vertical(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(migrated_engine)
    _profile(migrated_engine)
    client, calls = _switch_client(migrated_engine, user, monkeypatch)

    resp = client.patch("/api/me", json={"vertical": "underwater_basket_weaving"})

    assert resp.status_code == 404
    assert calls == []
    active = active_profile_for_user(migrated_engine, _EMAIL)
    assert active is not None and active.vertical == _VERTICAL


def test_patch_switch_409_without_a_profile(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Signed in but never onboarded: there is nothing to switch, and the answer is not a 500."""
    user = _user(migrated_engine)
    client, calls = _switch_client(migrated_engine, user, monkeypatch)

    resp = client.patch("/api/me", json={"vertical": _OTHER})

    assert resp.status_code == 409
    assert calls == []


def test_patch_switch_429_while_the_window_is_closed(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(migrated_engine)
    _profile(migrated_engine)
    _set_switch_clock(migrated_engine, user.id, datetime.now(UTC) - timedelta(hours=1))
    client, calls = _switch_client(migrated_engine, user, monkeypatch)

    resp = client.patch("/api/me", json={"vertical": _OTHER})

    assert resp.status_code == 429
    # Whole seconds, so the client can render a real countdown rather than a guess.
    assert int(resp.headers["Retry-After"]) > 0
    assert calls == []


def test_patch_switch_429_when_the_daily_budget_is_spent(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A switch pays the same global signup ceiling as an upload — that ceiling is exactly what the
    per-user clock exists to keep one user from exhausting."""
    monkeypatch.setenv("VJA_DAILY_LLM_BUDGET_USD", "0")
    user = _user(migrated_engine)
    _profile(migrated_engine)
    client, calls = _switch_client(migrated_engine, user, monkeypatch)

    resp = client.patch("/api/me", json={"vertical": _OTHER})

    assert resp.status_code == 429
    assert calls == []
    active = active_profile_for_user(migrated_engine, _EMAIL)
    assert active is not None and active.vertical == _VERTICAL


def test_patch_empty_body_is_422(migrated_engine: Engine) -> None:
    """A partial update with nothing in it is a client bug, not a silent success."""
    user = _user(migrated_engine)
    assert _client(migrated_engine, user).patch("/api/me", json={}).status_code == 422


def test_patch_applies_both_fields(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(migrated_engine)
    _profile(migrated_engine)
    client, _ = _switch_client(migrated_engine, user, monkeypatch)

    resp = client.patch("/api/me", json={"vertical": _OTHER, "digest_paused": True})

    assert resp.status_code == 200
    assert resp.json() == {"digest_paused": True, "vertical": _OTHER}
    assert _paused(migrated_engine, user.id)


def test_failed_switch_leaves_the_pause_flag_untouched(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch runs first precisely so a rejected one applies nothing at all."""
    user = _user(migrated_engine)
    _profile(migrated_engine)
    _set_switch_clock(migrated_engine, user.id, datetime.now(UTC) - timedelta(hours=1))
    client, _ = _switch_client(migrated_engine, user, monkeypatch)

    resp = client.patch("/api/me", json={"vertical": _OTHER, "digest_paused": True})

    assert resp.status_code == 429
    assert not _paused(migrated_engine, user.id)
