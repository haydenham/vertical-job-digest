"""Unit tests for apply-link verification (P3B1, D-008).

HTTP stubbed by respx — no real packets. The gate's rule: resolve to <400 (after HEAD,
falling back to GET on method-not-allowed); any error or 4xx/5xx is a failure.
"""

import httpx
import respx

from vja.digest.verification import verify_apply_url

_URL = "https://jobs.example.com/123"


@respx.mock
def test_head_200_passes() -> None:
    respx.head(_URL).mock(return_value=httpx.Response(200))
    with httpx.Client() as client:
        assert verify_apply_url(_URL, client) is True


@respx.mock
def test_head_405_falls_back_to_get() -> None:
    respx.head(_URL).mock(return_value=httpx.Response(405))
    get_route = respx.get(_URL).mock(return_value=httpx.Response(200))
    with httpx.Client() as client:
        assert verify_apply_url(_URL, client) is True
    assert get_route.called


@respx.mock
def test_redirect_to_200_passes() -> None:
    respx.head(_URL).mock(
        return_value=httpx.Response(301, headers={"Location": "https://jobs.example.com/final"})
    )
    respx.head("https://jobs.example.com/final").mock(return_value=httpx.Response(200))
    with httpx.Client() as client:
        assert verify_apply_url(_URL, client) is True


@respx.mock
def test_404_fails() -> None:
    respx.head(_URL).mock(return_value=httpx.Response(404))
    with httpx.Client() as client:
        assert verify_apply_url(_URL, client) is False


@respx.mock
def test_connection_error_fails() -> None:
    respx.head(_URL).mock(side_effect=httpx.ConnectError("boom"))
    with httpx.Client() as client:
        assert verify_apply_url(_URL, client) is False


@respx.mock
def test_server_error_fails() -> None:
    respx.head(_URL).mock(return_value=httpx.Response(500))
    with httpx.Client() as client:
        assert verify_apply_url(_URL, client) is False
