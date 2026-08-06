"""Apply-link verification (D-008, refined by D-110): a posting never ships on a dead link.

"One fake posting costs more trust than ten real ones earn." The gate holds — but *what counts
as dead* is now narrow, because collapsing every failure into one `bool` was losing roughly one
in five matched roles.

**Only a definitive 404/410 is dead.** A 401/403 means a WAF refused *us* (measured 2026-08-06:
Coinbase, Akuna and Tower Research 403 every method and every User-Agent while the pages load in
a browser); a 429/5xx/timeout means we could not complete the check. Neither is evidence the job
is gone — and Layer 1 listed the posting within the last four hours or the diff would have closed
it, so the digest is a *second* opinion on a link, not the only one. Since the send window only
moves forward (`last_sent_at`), one unlucky check used to remove a role from every future digest
while the dashboard, which never verifies anything, kept showing it. That asymmetry was the bug.

`ApplyLinkVerifier` is the job-scoped entry point: one client, one check per URL per job, and
per-host spacing. Before it, `send_main` re-verified every candidate once *per recipient* — 2,727
requests for 462 distinct URLs, over half of them at two Greenhouse hosts, in one unbroken burst.
The quarantine spikes landed exactly on the big baseline digests, which is what a rate limit looks
like from the outside.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable
from enum import StrEnum
from types import TracebackType
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("vja.digest.verification")

_TIMEOUT = 10.0
_USER_AGENT = "vja-job-agent/0.0.1 (+https://github.com/haydenham/vertical-job-digest)"

# Politeness (docs/05) *and* the fix: minimum gap between two requests to the same host.
_HOST_INTERVAL_SECONDS = 0.25
# Backoff before each retry of an inconclusive check. Two retries, widening — a rate limit needs
# seconds to clear, and the whole job has an hour.
_RETRY_BACKOFF_SECONDS = (2.0, 5.0)
# Ceiling on time spent *retrying* across the whole job. Retries are worth seconds, not the send:
# if a host throttles everything, 462 URLs x 7s would push a ~6 minute job past the Job's 1h task
# timeout, and a timed-out digest sends nothing at all — strictly worse than the bug being fixed.
# Past the budget an inconclusive check ships immediately, which is where it was heading anyway.
_RETRY_BUDGET_SECONDS = 300.0

_DEAD_STATUSES = frozenset({404, 410})
_BLOCKED_STATUSES = frozenset({401, 403})
_METHOD_NOT_ALLOWED_STATUSES = frozenset({405, 501})


class LinkCheck(StrEnum):
    """What one HTTP check actually established about an apply link."""

    ALIVE = "alive"  # resolved < 400
    DEAD = "dead"  # 404/410 — the link is gone. The only outcome that quarantines.
    BLOCKED = "blocked"  # 401/403 — we were refused; says nothing about the job.
    UNKNOWN = "unknown"  # 429/5xx/other/transport — the check did not complete.


def _describe(status: int | None) -> str:
    """A status code for the log, or the reason there isn't one."""
    return str(status) if status is not None else "transport error"


def check_apply_url(url: str, client: httpx.Client) -> tuple[LinkCheck, int | None]:
    """Classify `url`, returning the outcome and the status code that produced it.

    Tries a cheap HEAD first (following redirects); if the server rejects the method (405/501),
    retries with GET. The status code is returned rather than discarded because it is the one
    thing that was missing when this was diagnosed: "throttled" had to be inferred from burst
    shape and clean re-checks, since nothing recorded what the server actually said.
    """
    try:
        response = client.head(url, follow_redirects=True, timeout=_TIMEOUT)
        if response.status_code in _METHOD_NOT_ALLOWED_STATUSES:
            response = client.get(url, follow_redirects=True, timeout=_TIMEOUT)
    except httpx.HTTPError:
        return LinkCheck.UNKNOWN, None

    status = response.status_code
    if status < 400:
        return LinkCheck.ALIVE, status
    if status in _DEAD_STATUSES:
        return LinkCheck.DEAD, status
    if status in _BLOCKED_STATUSES:
        return LinkCheck.BLOCKED, status
    return LinkCheck.UNKNOWN, status


def verify_apply_url(url: str, client: httpx.Client) -> bool:
    """True iff `url` may be shipped after **one** check: no retry, no throttle.

    The single-shot path, kept for `assembly.py`'s fallback when no job-scoped verifier was
    passed (a debugging run, a single `build_digest` call). The scheduled Jobs use
    `ApplyLinkVerifier`, which is this plus caching, spacing and retries.

    An `UNKNOWN` fails here but *ships* from the verifier, and the asymmetry is deliberate:
    shipping a link we could not confirm is justified only by having tried three times over
    several seconds. Without retries, "when in doubt, don't ship" still stands. A `BLOCKED`
    ships either way — no number of retries will change a WAF's mind.
    """
    outcome, _status = check_apply_url(url, client)
    return outcome in (LinkCheck.ALIVE, LinkCheck.BLOCKED)


def default_client() -> httpx.Client:
    """A client with an identifiable User-Agent (politeness — `docs/05`)."""
    return httpx.Client(headers={"User-Agent": _USER_AGENT})


class ApplyLinkVerifier:
    """Job-scoped apply-link verification: one check per URL, spaced per host, retried when unclear.

    Callable as `(str) -> bool`, so it drops into the existing `verify` seam that `build_digest`,
    `send_digest` and `run_nightly` already thread — the whole change is *which* callable they get.

    Three things it adds over `verify_apply_url`:

    1. **One check per URL per job.** Eleven trading users each triggered their own check of the
       same Jane Street link; the cache makes recipients after the first free.
    2. **Per-host spacing**, which is the standing politeness rule this code was violating.
    3. **Retries on an inconclusive result**, so a rate limit costs seconds rather than the role.

    `sleep` is injected so tests exercise the real retry and spacing logic without real waits.
    """

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        host_interval: float = _HOST_INTERVAL_SECONDS,
        backoffs: tuple[float, ...] = _RETRY_BACKOFF_SECONDS,
        retry_budget: float = _RETRY_BUDGET_SECONDS,
    ) -> None:
        self._client = client if client is not None else default_client()
        self._owns_client = client is None
        self._sleep = sleep
        self._monotonic = monotonic
        self._host_interval = host_interval
        self._backoffs = backoffs
        self._retry_budget = retry_budget
        self._retry_spent = 0.0
        self._budget_warned = False
        self._results: dict[str, bool] = {}
        self._last_request_at: dict[str, float] = {}
        self.outcomes: Counter[str] = Counter()
        self.cache_hits = 0

    def __call__(self, url: str) -> bool:
        cached = self._results.get(url)
        if cached is not None:
            self.cache_hits += 1
            return cached
        verdict = self._verify(url)
        self._results[url] = verdict
        return verdict

    def _verify(self, url: str) -> bool:
        outcome = LinkCheck.UNKNOWN
        status: int | None = None
        attempts = 0
        # One initial attempt plus one per backoff; only an inconclusive result is worth repeating.
        for backoff in (None, *self._backoffs):
            if backoff is not None and not self._spend_retry_budget(backoff):
                break
            self._wait_for_host(url)
            outcome, status = check_apply_url(url, self._client)
            attempts += 1
            if outcome is not LinkCheck.UNKNOWN:
                break
            logger.info(
                "apply-link check inconclusive (attempt %d, status %s): %s",
                attempts,
                _describe(status),
                url,
            )

        self.outcomes[outcome.value] += 1
        if outcome is LinkCheck.DEAD:
            logger.warning("apply link is dead (%s), quarantining: %s", status, url)
        elif outcome is LinkCheck.BLOCKED:
            logger.warning("apply link blocked us (%s), shipping anyway: %s", status, url)
        elif outcome is LinkCheck.UNKNOWN:
            # `attempts` is the real count, which is not `len(backoffs) + 1` once the budget runs
            # out — and this line is what gets read when diagnosing the next bad morning.
            logger.warning(
                "apply link unverifiable after %d attempt(s) (last: %s), shipping anyway: %s",
                attempts,
                _describe(status),
                url,
            )
        # Everything except a definitive DEAD ships (D-110). Having exhausted the retries is what
        # earns an UNKNOWN its place in the email; see `verify_apply_url` on the asymmetry.
        return outcome is not LinkCheck.DEAD

    def _spend_retry_budget(self, backoff: float) -> bool:
        """Charge `backoff` to the job's retry budget; False when there isn't room to retry.

        Warned once per job, not once per URL: past the budget every remaining inconclusive link
        takes this path, and a line each would bury the per-URL diagnostics under itself.
        """
        if self._retry_spent + backoff > self._retry_budget:
            if not self._budget_warned:
                self._budget_warned = True
                logger.warning(
                    "retry budget of %.0fs is spent; remaining unverifiable links ship unretried",
                    self._retry_budget,
                )
            return False
        self._retry_spent += backoff
        self._sleep(backoff)
        return True

    def _wait_for_host(self, url: str) -> None:
        """Hold each host to one request per `host_interval` — politeness, and the burst fix."""
        host = urlparse(url).netloc
        last = self._last_request_at.get(host)
        now = self._monotonic()
        if last is not None:
            remaining = self._host_interval - (now - last)
            if remaining > 0:
                self._sleep(remaining)
                now = self._monotonic()
        self._last_request_at[host] = now

    def summary(self) -> str:
        """One line for the job log: what the checks found, and what the cache saved.

        The digest's own record cannot carry this. A send with 0 new, 0 closed and N quarantined
        returns `skipped` and writes no `digests` row at all (D-028), so before this line an
        all-quarantine morning left no durable evidence anywhere.
        """
        counts = " ".join(f"{name}={self.outcomes[name]}" for name in sorted(self.outcomes))
        checked = sum(self.outcomes.values())
        return (
            f"apply-link verification: {checked} URLs checked ({counts or 'none'}), "
            f"{self.cache_hits} repeat lookups served from cache"
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ApplyLinkVerifier:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
