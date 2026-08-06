"""Unit tests for apply-link verification (P3B1, D-008, D-110).

HTTP stubbed by respx — no real packets. The single-shot `verify_apply_url` resolves <400
(after HEAD, falling back to GET on method-not-allowed); an error or 4xx/5xx fails, except a
401/403 block, which ships. `ApplyLinkVerifier` adds the job-scoped behavior: one check per URL,
per-host spacing, retries on an inconclusive result, and shipping what it could not confirm.

Time is injected throughout, so the real retry and spacing logic runs with no real waiting.
"""

import httpx
import respx

from vja.digest.verification import ApplyLinkVerifier, LinkCheck, check_apply_url, verify_apply_url

_URL = "https://jobs.example.com/123"
_OTHER_HOST = "https://other.example.com/456"


class _Clock:
    """A recording stand-in for `time.sleep` + `time.monotonic` (no real waiting in tests)."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _verifier(
    clock: _Clock,
    *,
    backoffs: tuple[float, ...] = (2.0, 5.0),
    host_interval: float = 0.25,
    retry_budget: float = 300.0,
) -> ApplyLinkVerifier:
    return ApplyLinkVerifier(
        httpx.Client(),
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        host_interval=host_interval,
        backoffs=backoffs,
        retry_budget=retry_budget,
    )


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


@respx.mock
def test_403_ships_because_a_block_is_not_a_dead_job() -> None:
    """A WAF 403 says we were not allowed to look, not that the job is gone (D-110).

    Measured on 2026-08-06: Coinbase, Akuna and Tower Research return 403 to HEAD *and* GET,
    with our User-Agent and with none, while the pages load in a browser and Layer 1 listed
    the postings hours earlier. Quarantining these deleted whole employers from every digest.
    """
    respx.head(_URL).mock(return_value=httpx.Response(403))
    with httpx.Client() as client:
        assert verify_apply_url(_URL, client) is True


@respx.mock
def test_check_reports_the_status_code_that_produced_the_outcome() -> None:
    """The code itself is the point: before D-110 nothing recorded what the server said."""
    respx.head(_URL).mock(return_value=httpx.Response(429))
    with httpx.Client() as client:
        assert check_apply_url(_URL, client) == (LinkCheck.UNKNOWN, 429)


@respx.mock
def test_check_classifies_a_transport_failure_without_a_status() -> None:
    respx.head(_URL).mock(side_effect=httpx.ConnectError("boom"))
    with httpx.Client() as client:
        assert check_apply_url(_URL, client) == (LinkCheck.UNKNOWN, None)


# --- ApplyLinkVerifier: the job-scoped path the scheduled Jobs actually use ------------------


@respx.mock
def test_a_dead_link_is_still_quarantined_and_never_retried() -> None:
    """The D-008 control case. If this assertion ever flips, the fix went too far.

    The no-retry half matters too: a 404 is an answer, and re-asking it three times would triple
    the request volume the rest of this class exists to cut.
    """
    route = respx.head(_URL).mock(return_value=httpx.Response(404))
    clock = _Clock()
    with _verifier(clock) as verify:
        assert verify(_URL) is False
    assert route.call_count == 1
    assert clock.slept == []


@respx.mock
def test_an_inconclusive_link_is_retried_then_shipped() -> None:
    """A 429/5xx is "we could not tell", not "it is dead" — and it used to cost the role forever.

    Shipping is earned by the retries: three attempts across seven seconds of backoff.
    """
    route = respx.head(_URL).mock(return_value=httpx.Response(503))
    clock = _Clock()
    with _verifier(clock) as verify:
        assert verify(_URL) is True
    assert route.call_count == 3
    assert clock.slept[:2] == [2.0, 5.0]  # the backoffs, widening


@respx.mock
def test_a_recovered_link_stops_retrying_as_soon_as_it_resolves() -> None:
    route = respx.head(_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200), httpx.Response(500)]
    )
    clock = _Clock()
    with _verifier(clock) as verify:
        assert verify(_URL) is True
    assert route.call_count == 2


@respx.mock
def test_a_blocked_link_ships_without_burning_retries() -> None:
    """No number of retries changes a WAF's mind: a 403 is final, just not fatal."""
    route = respx.head(_URL).mock(return_value=httpx.Response(403))
    clock = _Clock()
    with _verifier(clock) as verify:
        assert verify(_URL) is True
    assert route.call_count == 1


@respx.mock
def test_each_url_is_checked_once_per_job_however_many_recipients_share_it() -> None:
    """The 5.9x duplication fix: 2,727 requests for 462 distinct URLs, once per recipient."""
    route = respx.head(_URL).mock(return_value=httpx.Response(200))
    clock = _Clock()
    with _verifier(clock) as verify:
        assert [verify(_URL) for _ in range(4)] == [True, True, True, True]
    assert route.call_count == 1
    assert verify.cache_hits == 3


@respx.mock
def test_a_quarantine_decision_is_cached_too_not_just_a_pass() -> None:
    route = respx.head(_URL).mock(return_value=httpx.Response(404))
    clock = _Clock()
    with _verifier(clock) as verify:
        assert [verify(_URL), verify(_URL)] == [False, False]
    assert route.call_count == 1


@respx.mock
def test_requests_to_one_host_are_spaced_but_different_hosts_are_not() -> None:
    respx.head(_URL).mock(return_value=httpx.Response(200))
    respx.head(_URL + "x").mock(return_value=httpx.Response(200))
    respx.head(_OTHER_HOST).mock(return_value=httpx.Response(200))
    clock = _Clock()
    with _verifier(clock, host_interval=0.25) as verify:
        verify(_URL)
        verify(_OTHER_HOST)  # a different host: no reason to wait
        assert clock.slept == []
        verify(_URL + "x")  # same host as the first: hold the interval
    assert clock.slept == [0.25]


@respx.mock
def test_a_host_left_idle_long_enough_is_not_delayed() -> None:
    respx.head(_URL).mock(return_value=httpx.Response(200))
    respx.head(_URL + "x").mock(return_value=httpx.Response(200))
    clock = _Clock()
    with _verifier(clock, host_interval=0.25) as verify:
        verify(_URL)
        clock.advance(1.0)  # the rest of the job took a while
        verify(_URL + "x")
    assert clock.slept == []


@respx.mock
def test_retries_stop_once_the_job_budget_is_spent() -> None:
    """Retries are worth seconds, never the send.

    A host throttling everything would otherwise push the job past its 1h task timeout, and a
    timed-out digest sends nothing at all — strictly worse than the bug this fixes. Past the
    budget an inconclusive link ships immediately, which is where it was heading anyway.
    """
    route = respx.head(_URL).mock(return_value=httpx.Response(503))
    other = respx.head(_OTHER_HOST).mock(return_value=httpx.Response(503))
    clock = _Clock()
    # Budget fits exactly one URL's two backoffs (2 + 5), so the second URL gets none.
    with _verifier(clock, backoffs=(2.0, 5.0), retry_budget=7.0) as verify:
        assert verify(_URL) is True
        assert verify(_OTHER_HOST) is True

    assert route.call_count == 3  # full retries
    assert other.call_count == 1  # budget spent: one attempt, then ship
    assert sum(clock.slept) == 7.0


@respx.mock
def test_summary_counts_every_outcome_and_the_cache_savings() -> None:
    """The job log line. A quarantine-only send writes no `digests` row (D-028), so without
    this the morning leaves no durable evidence at all."""
    respx.head(_URL).mock(return_value=httpx.Response(200))
    respx.head(_OTHER_HOST).mock(return_value=httpx.Response(404))
    clock = _Clock()
    with _verifier(clock) as verify:
        verify(_URL)
        verify(_URL)
        verify(_OTHER_HOST)

    assert verify.outcomes == {"alive": 1, "dead": 1}
    summary = verify.summary()
    assert "2 URLs checked" in summary
    assert "alive=1" in summary
    assert "dead=1" in summary
    assert "1 repeat lookups served from cache" in summary
