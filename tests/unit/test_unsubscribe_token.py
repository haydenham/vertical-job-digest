"""The digest unsubscribe token (D-094): signed round-trip, tamper rejection, URL building.

Pure unit level — the module is deterministic given `VJA_SESSION_SECRET`, no DB/network. Invalid
tokens must come back as None (never raise): the parser fronts a public no-login endpoint.
"""

import pytest
from itsdangerous import URLSafeSerializer

from vja.digest.unsubscribe import (
    UnsubscribeClaim,
    make_unsubscribe_token,
    parse_unsubscribe_token,
    unsubscribe_url,
)

_SECRET = "unit-test-secret"


@pytest.fixture(autouse=True)
def _pin_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VJA_SESSION_SECRET", _SECRET)


def test_round_trip_yields_the_claim() -> None:
    token = make_unsubscribe_token(42, "me@example.com")
    assert parse_unsubscribe_token(token) == UnsubscribeClaim(user_id=42, email="me@example.com")


def test_tampered_and_garbage_tokens_parse_to_none() -> None:
    token = make_unsubscribe_token(42, "me@example.com")
    assert parse_unsubscribe_token(token[:-2] + "xx") is None
    assert parse_unsubscribe_token("not-a-token") is None
    assert parse_unsubscribe_token("") is None


def test_token_signed_with_another_secret_is_rejected() -> None:
    forged = URLSafeSerializer("some-other-secret", salt="digest-unsubscribe").dumps(
        {"uid": 42, "email": "me@example.com"}
    )
    assert parse_unsubscribe_token(forged) is None


def test_wrong_payload_shape_parses_to_none() -> None:
    # Correctly signed (same secret + salt) but not the {uid:int, email:str} claim.
    signer = URLSafeSerializer(_SECRET, salt="digest-unsubscribe")
    for payload in (["me@example.com"], {"uid": "42", "email": "me@example.com"}, {"uid": 42}, 42):
        assert parse_unsubscribe_token(signer.dumps(payload)) is None


def test_unsubscribe_url_joins_and_encodes() -> None:
    assert unsubscribe_url("https://role-feed.com", "a+b/c") == (
        "https://role-feed.com/unsubscribe?token=a%2Bb%2Fc"
    )
    # Trailing slash on the base must not double up.
    assert unsubscribe_url("https://role-feed.com/", "t").startswith(
        "https://role-feed.com/unsubscribe?token="
    )
