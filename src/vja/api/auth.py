"""Auth foundation for the dashboard API (Phase 9.2, D-055).

Google OAuth (OIDC) login → a signed-cookie session carrying `user_id`, plus the dependency that
resolves the current user. Lives in the `api` layer (top of the import stack; depends down on
`vja.db.users`). Login routes are **inert until configured** (`GOOGLE_CLIENT_*`), and the default
test suite mocks the token exchange — no live Google in the inner loop.

Enforcement is **deferred** (D-055): `VJA_AUTH_REQUIRED` (default off) is the seam the read API
checks, so the local dashboard stays usable before the login frontend (9.4) / deploy flip it on.
"""

from __future__ import annotations

import logging
import os

from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException, Request

from vja.db.users import User, get_user

logger = logging.getLogger(__name__)

_GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"
_DEV_SESSION_SECRET = "dev-insecure-session-secret-change-me"  # noqa: S105
_DEFAULT_SESSION_MAX_AGE = 14 * 24 * 3600  # 14 days (Starlette's own default)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def session_secret() -> str:
    """The cookie-signing secret. Falls back to an insecure dev value with a loud warning — a real
    deploy must set `VJA_SESSION_SECRET` (9.5)."""
    secret = os.environ.get("VJA_SESSION_SECRET")
    if secret:
        return secret
    logger.warning("VJA_SESSION_SECRET unset — using an insecure dev secret. Set it before deploy.")
    return _DEV_SESSION_SECRET


def cookie_https_only() -> bool:
    """Whether the session cookie is `Secure` (HTTPS-only). Off by default so dev over http://localhost
    works; set `VJA_COOKIE_SECURE=1` in prod (behind TLS). (9.5a, D-059)"""
    return _env_truthy("VJA_COOKIE_SECURE")


def session_max_age() -> int:
    """Session-cookie lifetime in seconds (`VJA_SESSION_MAX_AGE`, default 14 days). (9.5a, D-059)"""
    raw = os.environ.get("VJA_SESSION_MAX_AGE")
    return int(raw) if raw else _DEFAULT_SESSION_MAX_AGE


def oauth_redirect_uri(request: Request) -> str:
    """The OAuth callback URI Google redirects back to. Prefers the explicit `VJA_PUBLIC_BASE_URL`
    (the prod public origin) so it is correct behind Cloud Run's TLS terminator — where
    `request.url_for` would otherwise yield an `http://` URI and trip a `redirect_uri_mismatch`.
    Falls back to `url_for` for local dev. (9.5a, D-059)"""
    base = os.environ.get("VJA_PUBLIC_BASE_URL")
    if base:
        return f"{base.rstrip('/')}/auth/callback"
    return str(request.url_for("auth_callback"))


def auth_required() -> bool:
    """The enforcement seam (D-055). When true, protected reads 401 without a session."""
    return _env_truthy("VJA_AUTH_REQUIRED")


def build_oauth() -> OAuth | None:
    """An Authlib registry with Google registered, or None when `GOOGLE_CLIENT_*` are unset (login
    routes then return 503). OIDC discovery is lazy — no network until a login is attempted."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not (client_id and client_secret):
        return None
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=_GOOGLE_METADATA_URL,
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth


def get_current_user(request: Request) -> User | None:
    """The authenticated user from the session cookie, or None. A stale `user_id` (deleted user)
    resolves to None. Usable as a FastAPI dependency."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return get_user(request.app.state.engine, int(user_id))


def require_user(request: Request) -> User:
    """Dependency for endpoints that must be authed (the 9.3 write endpoints). 401 if no session."""
    user = get_current_user(request)
    if user is None:
        raise HTTPException(401, "authentication required")
    return user
