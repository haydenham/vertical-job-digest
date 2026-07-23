"""Signed no-login unsubscribe tokens for the digest email footer (D-094).

The digest composer (nightly Job) mints a token per recipient; the API's `/unsubscribe`
endpoints parse it back. Both sides live off the same secret — `VJA_SESSION_SECRET`, the
cookie-signing secret (`vja.api.auth.session_secret` mirrors this resolution; keep them in
lockstep) — so the composer and the endpoint can never disagree about the key. Tokens are
deliberately non-expiring: an unsubscribe link in an old digest email must keep working.
Rotating the session secret invalidates outstanding links (accepted trade-off).

The payload carries `{uid, email}`; the endpoint applies the flag only where *both* match the
current `users` row, so a stale token (deleted/changed account) can't pause someone else.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from urllib.parse import quote

from itsdangerous import BadSignature, URLSafeSerializer

logger = logging.getLogger(__name__)

_SALT = "digest-unsubscribe"
# Same fallback constant as vja.api.auth._DEV_SESSION_SECRET — a real deploy sets the env var
# on both the API service and the nightly Job (ship.sh mounts it on both).
_DEV_SESSION_SECRET = "dev-insecure-session-secret-change-me"  # noqa: S105


@dataclass(frozen=True)
class UnsubscribeClaim:
    user_id: int
    email: str


def _secret() -> str:
    secret = os.environ.get("VJA_SESSION_SECRET")
    if secret:
        return secret
    logger.warning(
        "VJA_SESSION_SECRET unset — unsubscribe tokens use an insecure dev secret. "
        "Set it before deploy."
    )
    return _DEV_SESSION_SECRET


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(_secret(), salt=_SALT)


def make_unsubscribe_token(user_id: int, email: str) -> str:
    """A URL-safe signed token identifying one user's unsubscribe authorization."""
    token = _serializer().dumps({"uid": user_id, "email": email})
    assert isinstance(token, str)
    return token


def parse_unsubscribe_token(token: str) -> UnsubscribeClaim | None:
    """The claim inside a token, or None for anything tampered/garbage/wrong-shaped.
    Never raises — invalid tokens are an expected input at a public endpoint."""
    try:
        payload = _serializer().loads(token)
    except BadSignature:
        return None
    if not isinstance(payload, dict):
        return None
    uid, email = payload.get("uid"), payload.get("email")
    if not isinstance(uid, int) or isinstance(uid, bool) or not isinstance(email, str):
        return None
    return UnsubscribeClaim(user_id=uid, email=email)


def unsubscribe_url(base_url: str, token: str) -> str:
    """The absolute footer link: `{base}/unsubscribe?token={token}`."""
    return f"{base_url.rstrip('/')}/unsubscribe?token={quote(token, safe='')}"
