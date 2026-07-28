"""Integration tests for `POST /api/feedback` (D-100) — the third write surface.

The endpoint stores nothing: it resolves the reporter's context server-side and emails one report
to the ops recipient. So the assertions are about the *guards* (login, length, provider failure)
and about which context the server attaches rather than trusts from the client.

Auth is injected via dependency override, matching `test_settings_api.py`; the real-session flow
is pinned in `test_auth.py`. `load_config` is patched rather than driven by env because the repo's
own `.env` would otherwise leak a real Resend key into the unconfigured-server case.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from vja.api.app import create_app
from vja.api.auth import get_current_user, require_user
from vja.db.profiles import upsert_profile
from vja.db.users import User, upsert_user_by_google
from vja.digest.feedback import FEEDBACK_MAX_CHARS
from vja.digest.render import RenderedEmail
from vja.digest.send import ConfigError, DigestConfig, SendError

_VERTICAL = "grid_power_software"
_EMAIL = "beta@example.com"
_CONFIG = DigestConfig(api_key="k", sender="digest@role-feed.com", recipient="ops@example.com")
_BODY = {"category": "bug", "message": "The top row's apply link 404s.", "page": "/dashboard"}


def _user(engine: Engine, email: str = _EMAIL) -> User:
    return upsert_user_by_google(engine, google_sub=f"g-{email}", email=email, name="Beta User")


def _profile(engine: Engine, email: str = _EMAIL) -> None:
    upsert_profile(
        engine, user_email=email, vertical=_VERTICAL, resume_text=email, domain_vocabulary=[]
    )


def _client(engine: Engine, user: User | None = None) -> TestClient:
    app = create_app(engine)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[require_user] = lambda: user
    return TestClient(app)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture what would have gone to Resend, with mail config forced to a known-good value."""
    captured: list[dict[str, Any]] = []

    def fake_send(
        config: DigestConfig,
        rendered: RenderedEmail,
        *,
        recipient: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        captured.append(
            {
                "recipient": recipient or config.recipient,
                "subject": rendered.subject,
                "text": rendered.text,
                "html": rendered.html,
                "headers": headers,
            }
        )

    monkeypatch.setattr("vja.digest.feedback.send_email", fake_send)
    monkeypatch.setattr("vja.api.app.load_config", lambda: _CONFIG)
    return captured


# --- the guard: only signed-in users can report ------------------------------------------------


def test_feedback_requires_a_session(migrated_engine: Engine, sent: list[dict[str, Any]]) -> None:
    resp = _client(migrated_engine).post("/api/feedback", json=_BODY)
    assert resp.status_code == 401
    assert sent == []


# --- the happy path ----------------------------------------------------------------------------


def test_feedback_emails_the_ops_recipient_with_server_resolved_context(
    migrated_engine: Engine, sent: list[dict[str, Any]]
) -> None:
    user = _user(migrated_engine)
    _profile(migrated_engine)
    client = _client(migrated_engine, user)

    resp = client.post("/api/feedback", json=_BODY, headers={"User-Agent": "Firefox/141.0"})

    assert resp.status_code == 202
    assert resp.json() == {"status": "sent"}
    (email,) = sent
    assert email["recipient"] == "ops@example.com"
    assert email["headers"] == {"Reply-To": _EMAIL}
    assert email["subject"] == f"Rolefeed feedback (bug) from {_EMAIL}"
    # What the client sent...
    assert "The top row's apply link 404s." in email["text"]
    assert "/dashboard" in email["text"]
    # ...and what the server attached rather than trusted.
    assert _EMAIL in email["text"]
    assert _VERTICAL in email["text"]
    assert "Firefox/141.0" in email["text"]


def test_feedback_from_a_user_with_no_profile_still_sends(
    migrated_engine: Engine, sent: list[dict[str, Any]]
) -> None:
    """Someone stuck in onboarding is exactly who needs to report a bug, so no profile gate."""
    client = _client(migrated_engine, _user(migrated_engine))

    resp = client.post("/api/feedback", json={"category": "confusing", "message": "Stuck here."})

    assert resp.status_code == 202
    (email,) = sent
    assert "(not onboarded)" in email["text"]


def test_identity_comes_from_the_session_not_the_request_body(
    migrated_engine: Engine, sent: list[dict[str, Any]]
) -> None:
    """Extra fields must not let a caller report as somebody else."""
    client = _client(migrated_engine, _user(migrated_engine))

    resp = client.post(
        "/api/feedback",
        json=_BODY | {"user_email": "victim@example.com", "vertical": "trading_software"},
    )

    assert resp.status_code == 202
    (email,) = sent
    assert "victim@example.com" not in email["text"]
    assert "trading_software" not in email["text"]
    assert _EMAIL in email["text"]


@pytest.mark.parametrize("category", ["bug", "idea", "confusing", "other"])
def test_every_category_is_accepted(
    migrated_engine: Engine, sent: list[dict[str, Any]], category: str
) -> None:
    client = _client(migrated_engine, _user(migrated_engine))
    resp = client.post("/api/feedback", json={"category": category, "message": "hi"})
    assert resp.status_code == 202
    assert sent[0]["subject"].startswith(f"Rolefeed feedback ({category})")


# --- the length cap, which is the whole abuse guard beyond require_user -------------------------


@pytest.mark.parametrize("message", ["", "   ", "\n\t "])
def test_an_empty_message_is_rejected(
    migrated_engine: Engine, sent: list[dict[str, Any]], message: str
) -> None:
    client = _client(migrated_engine, _user(migrated_engine))
    resp = client.post("/api/feedback", json={"category": "bug", "message": message})
    assert resp.status_code == 422
    assert sent == []


def test_a_message_at_the_cap_is_accepted_and_one_over_is_not(
    migrated_engine: Engine, sent: list[dict[str, Any]]
) -> None:
    client = _client(migrated_engine, _user(migrated_engine))

    at_cap = client.post(
        "/api/feedback", json={"category": "bug", "message": "x" * FEEDBACK_MAX_CHARS}
    )
    over = client.post(
        "/api/feedback", json={"category": "bug", "message": "x" * (FEEDBACK_MAX_CHARS + 1)}
    )

    assert at_cap.status_code == 202
    assert over.status_code == 422
    assert len(sent) == 1


def test_an_unknown_category_is_rejected(
    migrated_engine: Engine, sent: list[dict[str, Any]]
) -> None:
    client = _client(migrated_engine, _user(migrated_engine))
    resp = client.post("/api/feedback", json={"category": "complaint", "message": "hi"})
    assert resp.status_code == 422
    assert sent == []


# --- provider failures stay retryable -----------------------------------------------------------


def test_a_provider_failure_is_a_502(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch, sent: list[dict[str, Any]]
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise SendError("Resend returned 500: upstream is unhappy")

    monkeypatch.setattr("vja.digest.feedback.send_email", boom)
    client = _client(migrated_engine, _user(migrated_engine))

    resp = client.post("/api/feedback", json=_BODY)

    assert resp.status_code == 502
    assert "try again" in resp.json()["detail"]


def test_an_unconfigured_server_is_a_503(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch, sent: list[dict[str, Any]]
) -> None:
    """Dev without `RESEND_API_KEY`: not the user's fault and not a crash."""

    def unconfigured() -> DigestConfig:
        raise ConfigError("RESEND_API_KEY is not set")

    monkeypatch.setattr("vja.api.app.load_config", unconfigured)
    client = _client(migrated_engine, _user(migrated_engine))

    resp = client.post("/api/feedback", json=_BODY)

    assert resp.status_code == 503
    assert sent == []


# --- PII discipline ------------------------------------------------------------------------------


def test_the_message_body_is_never_logged(
    migrated_engine: Engine, sent: list[dict[str, Any]], caplog: pytest.LogCaptureFixture
) -> None:
    """Same rule the résumé path follows: log the outcome, not what the person wrote."""
    client = _client(migrated_engine, _user(migrated_engine))
    secret = "my salary is 123456 and I hate my manager"
    # Alembic's test-only fileConfig disables loggers imported before the migration ran, and
    # `migrated_engine` runs one (same dance as tests/unit/test_llm.py).
    logging.getLogger("vja.api.app").disabled = False

    with caplog.at_level(logging.DEBUG, logger="vja.api.app"):
        resp = client.post("/api/feedback", json={"category": "other", "message": secret})

    assert resp.status_code == 202

    assert secret not in caplog.text
    assert "feedback sent" in caplog.text
