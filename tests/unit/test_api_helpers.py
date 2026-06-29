"""Unit tests for the 9.5a deploy-hardening helpers (D-059): session-cookie flags, the OAuth
redirect-URI resolution (the Cloud-Run-behind-TLS fix), and the env-driven `vja-api` host/port
defaults. Pure functions — no DB, no network."""

from typing import cast
from unittest.mock import MagicMock

import pytest
from fastapi import Request

from vja.api.app import _parse_args
from vja.api.auth import cookie_https_only, oauth_redirect_uri, session_max_age


def test_cookie_https_only_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VJA_COOKIE_SECURE", raising=False)
    assert cookie_https_only() is False


@pytest.mark.parametrize("value", ["1", "true", "YES"])
def test_cookie_https_only_on_when_set(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("VJA_COOKIE_SECURE", value)
    assert cookie_https_only() is True


def test_session_max_age_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VJA_SESSION_MAX_AGE", raising=False)
    assert session_max_age() == 14 * 24 * 3600
    monkeypatch.setenv("VJA_SESSION_MAX_AGE", "3600")
    assert session_max_age() == 3600


def test_oauth_redirect_uri_prefers_public_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VJA_PUBLIC_BASE_URL", "https://rolefeed.com/")  # trailing slash trimmed
    mock = MagicMock()
    assert oauth_redirect_uri(cast("Request", mock)) == "https://rolefeed.com/auth/callback"
    mock.url_for.assert_not_called()


def test_oauth_redirect_uri_falls_back_to_url_for(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VJA_PUBLIC_BASE_URL", raising=False)
    mock = MagicMock()
    mock.url_for.return_value = "http://testserver/auth/callback"
    assert oauth_redirect_uri(cast("Request", mock)) == "http://testserver/auth/callback"
    mock.url_for.assert_called_once_with("auth_callback")


def test_parse_args_honours_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "8080")  # Cloud Run injects $PORT
    monkeypatch.setenv("VJA_API_HOST", "0.0.0.0")
    args = _parse_args([])
    assert args.host == "0.0.0.0"
    assert args.port == 8080


def test_parse_args_flags_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "8080")
    args = _parse_args(["--port", "9000", "--host", "127.0.0.1"])
    assert args.port == 9000
    assert args.host == "127.0.0.1"
