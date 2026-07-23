"""Auth foundation tests (Phase 9.2, D-055) — users repo + the OAuth login plumbing.

The live Google handshake (real token exchange + id_token verification) is a **manual** check
(run `vja-api`, hit `/auth/login` in a browser with real credentials) — consistent with the `live`
marker policy. Here we mock the Authlib client at the token boundary and exercise our own code:
the `users` repository, the callback's upsert+link+session, `/api/me`, logout, and the 503/redirect
wiring of `/auth/login`.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from vja.api.app import create_app
from vja.db.engine import begin
from vja.db.profiles import upsert_profile
from vja.db.schema import profiles, users
from vja.db.users import get_user, upsert_user_by_google

_VERTICAL = "grid_power_software"
_EMAIL = "me@example.com"


def _seed_email_profile(engine: Engine, email: str = _EMAIL) -> None:
    upsert_profile(
        engine, user_email=email, vertical=_VERTICAL, resume_text="r", domain_vocabulary=[]
    )


@pytest.fixture
def configured_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Env that makes the OAuth registry register Google (dummy creds; no network until login)."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("VJA_SESSION_SECRET", "test-session-secret")
    yield


# --- users repository ------------------------------------------------------------------------


def test_upsert_user_is_idempotent_on_google_sub(migrated_engine: Engine) -> None:
    first = upsert_user_by_google(migrated_engine, google_sub="g-1", email=_EMAIL, name="Me")
    again = upsert_user_by_google(migrated_engine, google_sub="g-1", email=_EMAIL, name="Me Again")
    assert first.id == again.id
    assert again.name == "Me Again"  # display name refreshed on repeat login


def test_first_login_adopts_email_only_user(migrated_engine: Engine) -> None:
    """A row that exists by email but has no google_sub is adopted (sub stamped), not duplicated."""
    with begin(migrated_engine) as conn:
        conn.execute(users.insert().values(email=_EMAIL, created_at=datetime.now(UTC)))
    user = upsert_user_by_google(migrated_engine, google_sub="g-1", email=_EMAIL, name="Me")
    assert user.google_sub == "g-1"
    # exactly one user row for this email
    with migrated_engine.connect() as conn:
        rows = conn.execute(select(users.c.id).where(users.c.email == _EMAIL)).all()
    assert len(rows) == 1


def test_login_links_existing_email_profile(migrated_engine: Engine) -> None:
    """Seed bridge (D-027→FK): an email-keyed profile gets `user_id` backfilled on first login."""
    _seed_email_profile(migrated_engine)
    user = upsert_user_by_google(migrated_engine, google_sub="g-1", email=_EMAIL)
    with migrated_engine.connect() as conn:
        linked = conn.execute(
            select(profiles.c.user_id).where(profiles.c.user_email == _EMAIL)
        ).scalar_one()
    assert linked == user.id


def test_get_user_missing_returns_none(migrated_engine: Engine) -> None:
    assert get_user(migrated_engine, 99999) is None


# --- OAuth login plumbing --------------------------------------------------------------------


def test_login_503_when_unconfigured(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No GOOGLE_CLIENT_* → the login route is inert (503), not a crash. (Explicitly cleared: the
    opt-in eval/e2e modules call load_dotenv() at import, which can leak a real .env in.)"""
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    client = TestClient(create_app(migrated_engine))
    assert client.get("/auth/login", follow_redirects=False).status_code == 503


def test_login_redirects_to_google(
    migrated_engine: Engine, configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(migrated_engine)

    captured: dict[str, object] = {}

    async def fake_authorize_redirect(
        request: object, redirect_uri: object, **kwargs: object
    ) -> RedirectResponse:
        captured["redirect_uri"] = str(redirect_uri)
        captured["kwargs"] = kwargs
        return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?client_id=test")

    monkeypatch.setattr(app.state.oauth.google, "authorize_redirect", fake_authorize_redirect)
    resp = TestClient(app).get("/auth/login", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers["location"]
    assert str(captured["redirect_uri"]).endswith("/auth/callback")  # our callback wired through
    # Account chooser forced (D-065) so a shared browser can't silently reuse a Google session.
    assert captured["kwargs"] == {"prompt": "select_account"}


def test_callback_creates_user_links_profile_and_opens_session(
    migrated_engine: Engine, configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_email_profile(migrated_engine)
    app = create_app(migrated_engine)

    async def fake_token(request: object) -> dict[str, object]:
        return {"userinfo": {"sub": "g-1", "email": _EMAIL, "name": "Me"}}

    monkeypatch.setattr(app.state.oauth.google, "authorize_access_token", fake_token)
    client = TestClient(app)

    resp = client.get("/auth/callback", follow_redirects=False)
    assert resp.status_code in (302, 307)

    # Session opened → /api/me resolves (TestClient carries the cookie across requests).
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == _EMAIL

    # Profile linked to the new user (the profile's user_id points at the upserted users row).
    with migrated_engine.connect() as conn:
        linked = conn.execute(
            select(profiles.c.user_id).where(profiles.c.user_email == _EMAIL)
        ).scalar_one()
        user_id = conn.execute(select(users.c.id).where(users.c.email == _EMAIL)).scalar_one()
    assert linked == user_id


def test_callback_400_when_userinfo_incomplete(
    migrated_engine: Engine, configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(migrated_engine)

    async def fake_token(request: object) -> dict[str, object]:
        return {"userinfo": {"sub": "g-1"}}  # missing email

    monkeypatch.setattr(app.state.oauth.google, "authorize_access_token", fake_token)
    assert TestClient(app).get("/auth/callback").status_code == 400


def test_me_401_without_session(migrated_engine: Engine) -> None:
    assert TestClient(create_app(migrated_engine)).get("/api/me").status_code == 401


def test_logout_clears_session(
    migrated_engine: Engine, configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(migrated_engine)

    async def fake_token(request: object) -> dict[str, object]:
        return {"userinfo": {"sub": "g-1", "email": _EMAIL, "name": "Me"}}

    monkeypatch.setattr(app.state.oauth.google, "authorize_access_token", fake_token)
    client = TestClient(app)
    client.get("/auth/callback")
    assert client.get("/api/me").status_code == 200

    client.post("/auth/logout")
    assert client.get("/api/me").status_code == 401


def test_delete_account_kills_real_session(
    migrated_engine: Engine, configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-094 deletion through the real cookie flow: after DELETE /api/me the session is dead
    (popped in-handler; a stale id would 401 anyway) and the users row is gone."""
    app = create_app(migrated_engine)

    async def fake_token(request: object) -> dict[str, object]:
        return {"userinfo": {"sub": "g-1", "email": _EMAIL, "name": "Me"}}

    monkeypatch.setattr(app.state.oauth.google, "authorize_access_token", fake_token)
    client = TestClient(app)
    client.get("/auth/callback")
    assert client.get("/api/me").status_code == 200

    assert client.delete("/api/me").status_code == 204
    assert client.get("/api/me").status_code == 401
    with migrated_engine.connect() as conn:
        assert conn.execute(select(users.c.id).where(users.c.email == _EMAIL)).first() is None
