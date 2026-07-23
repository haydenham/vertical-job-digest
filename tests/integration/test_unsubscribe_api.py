"""Integration tests for the no-login `/unsubscribe` endpoints (D-094).

The tokenized email-footer flow: GET renders a confirm page and never mutates (mail scanners
prefetch GETs); POST applies the pause — for both the confirm form and RFC-8058 one-click. All
invalid tokens get the same generic 400 (no user enumeration), and the routes stay reachable with
auth enforcement on and must not be shadowed by the SPA catch-all.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update

from vja.api.app import create_app
from vja.db.engine import begin
from vja.db.schema import users
from vja.db.users import User, upsert_user_by_google
from vja.digest.unsubscribe import make_unsubscribe_token

_EMAIL = "me@example.com"


@pytest.fixture(autouse=True)
def _pin_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VJA_SESSION_SECRET", "unsubscribe-api-secret")


def _user(engine: Engine, email: str = _EMAIL) -> User:
    return upsert_user_by_google(
        engine, google_sub=f"g-{email}", email=email, now=datetime(2026, 7, 1, tzinfo=UTC)
    )


def _paused(engine: Engine, user_id: int) -> bool:
    with engine.connect() as conn:
        return bool(
            conn.execute(select(users.c.digest_paused).where(users.c.id == user_id)).scalar_one()
        )


def test_get_renders_confirm_page_without_mutating(migrated_engine: Engine) -> None:
    user = _user(migrated_engine)
    token = make_unsubscribe_token(user.id, user.email)
    client = TestClient(create_app(migrated_engine))

    resp = client.get("/unsubscribe", params={"token": token})

    assert resp.status_code == 200
    assert _EMAIL in resp.text
    assert "method='post'" in resp.text
    assert not _paused(migrated_engine, user.id)  # a scanner prefetch changes nothing


def test_missing_or_garbage_token_gets_generic_400(migrated_engine: Engine) -> None:
    user = _user(migrated_engine)
    client = TestClient(create_app(migrated_engine))

    for resp in (
        client.get("/unsubscribe"),
        client.get("/unsubscribe", params={"token": "garbage"}),
        client.post("/unsubscribe"),
        client.post("/unsubscribe", params={"token": "garbage"}),
    ):
        assert resp.status_code == 400
        assert _EMAIL not in resp.text  # never reveals whether a user exists
    assert not _paused(migrated_engine, user.id)


def test_post_pauses_and_is_idempotent(migrated_engine: Engine) -> None:
    user = _user(migrated_engine)
    token = make_unsubscribe_token(user.id, user.email)
    client = TestClient(create_app(migrated_engine))

    first = client.post("/unsubscribe", params={"token": token})
    assert first.status_code == 200
    assert "unsubscribed" in first.text.lower()
    assert _paused(migrated_engine, user.id)

    again = client.post("/unsubscribe", params={"token": token})  # already paused → same page
    assert again.status_code == 200
    assert _paused(migrated_engine, user.id)


def test_rfc8058_one_click_post_body_pauses(migrated_engine: Engine) -> None:
    # Mail providers POST `List-Unsubscribe=One-Click` (form-encoded) to the List-Unsubscribe URL;
    # the body is ignored — the query token is the identity — but the POST must succeed.
    user = _user(migrated_engine)
    token = make_unsubscribe_token(user.id, user.email)
    client = TestClient(create_app(migrated_engine))

    resp = client.post(
        "/unsubscribe", params={"token": token}, data={"List-Unsubscribe": "One-Click"}
    )

    assert resp.status_code == 200
    assert _paused(migrated_engine, user.id)


def test_stale_token_email_mismatch_gets_400_and_no_change(migrated_engine: Engine) -> None:
    user = _user(migrated_engine)
    token = make_unsubscribe_token(user.id, user.email)
    with begin(migrated_engine) as conn:  # the account's email moved on since the digest went out
        conn.execute(update(users).where(users.c.id == user.id).values(email="new@example.com"))
    client = TestClient(create_app(migrated_engine))

    resp = client.post("/unsubscribe", params={"token": token})

    assert resp.status_code == 400
    assert not _paused(migrated_engine, user.id)


def test_unsubscribe_stays_no_login_with_auth_required(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The whole point is a working link for a logged-out email click (D-094), even in prod mode.
    monkeypatch.setenv("VJA_AUTH_REQUIRED", "1")
    user = _user(migrated_engine)
    token = make_unsubscribe_token(user.id, user.email)
    client = TestClient(create_app(migrated_engine))

    assert client.get("/unsubscribe", params={"token": token}).status_code == 200
    assert client.post("/unsubscribe", params={"token": token}).status_code == 200
    assert _paused(migrated_engine, user.id)


def test_spa_catch_all_does_not_shadow_unsubscribe(
    tmp_path: Path, migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # /unsubscribe is top-level (not under the catch-all's api//auth/ 404 prefixes); registration
    # order is what keeps it ahead of the SPA mount — pin it so a refactor can't regress it.
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>SPA</title>")
    monkeypatch.setenv("VJA_FRONTEND_DIST", str(dist))
    user = _user(migrated_engine)
    token = make_unsubscribe_token(user.id, user.email)
    client = TestClient(create_app(migrated_engine))

    resp = client.get("/unsubscribe", params={"token": token})
    assert resp.status_code == 200
    assert _EMAIL in resp.text and "SPA" not in resp.text

    bad = client.get("/unsubscribe", params={"token": "garbage"})
    assert bad.status_code == 400 and "SPA" not in bad.text
