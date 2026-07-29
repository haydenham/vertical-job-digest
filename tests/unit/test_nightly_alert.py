"""Unit tests for the nightly failure alert (P3B3).

`_failure_summary` is a pure string builder (no DB/network); `_send_failure_alert` posts via Resend
(stubbed by respx) and must never raise — if the alert itself can't send, it returns False.
"""

import json

import httpx
import respx

from vja.digest.send import DigestConfig, DigestSendResult, alert_failed_digests
from vja.nightly import _failure_summary, _send_failure_alert
from vja.pipeline import RunSummary

_CONFIG = DigestConfig(
    api_key="re_test", sender="onboarding@resend.dev", recipient="me@example.com"
)
_RESEND = "https://api.resend.com/emails"


def _run(status: str = "failed", fetch_failures: int = 2) -> RunSummary:
    return RunSummary(
        run_id=1,
        status=status,
        employers_fetched=3,
        fetch_failures=fetch_failures,
        postings_new=0,
        postings_reopened=0,
        postings_closed=0,
        results=[],
        errors=[{"employer_id": 5, "name": "Beta", "error": "FetchError('outage')"}],
    )


def test_failure_summary_includes_pipeline_fetch_and_digest_detail() -> None:
    digest = DigestSendResult(
        "grid_power_software", "hayden@example.com", "failed", None, 0, 0, 0, "Resend 422"
    )
    summary = _failure_summary(_run(), [digest])
    assert "status=failed" in summary
    assert "fetch_failures=2" in summary
    assert "Beta" in summary and "outage" in summary
    assert "digest [grid_power_software→hayden@example.com]: failed" in summary
    assert "Resend 422" in summary


@respx.mock
def test_send_failure_alert_posts_subject_with_counts() -> None:
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "x"}))
    assert _send_failure_alert(_CONFIG, _run(fetch_failures=3), []) is True
    sent = json.loads(route.calls.last.request.content)
    assert "FAILED" in sent["subject"]
    assert "3 fetch failures" in sent["subject"]


@respx.mock
def test_send_failure_alert_swallows_send_error() -> None:
    # If Resend itself is down, the alert can't send — but must not raise.
    respx.post(_RESEND).mock(return_value=httpx.Response(500, text="down"))
    assert _send_failure_alert(_CONFIG, _run(), []) is False


def test_digest_job_alerts_on_a_failed_send() -> None:
    """The standalone digest Job raises its own alarm (D-103).

    Before the split, a failed send was reported by the nightly composer that wrapped it. Once the
    digest is its own Cloud Run Job, nothing else in that process would say anything — `send_main`
    returned exit 1 and emailed nobody.
    """
    with respx.mock:
        route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "a"}))
        alerted = alert_failed_digests(
            _CONFIG,
            [
                DigestSendResult("grid_power_software", "a@example.com", "sent", 1, 2, 0, 0),
                DigestSendResult(
                    "aviation_software", "b@example.com", "failed", None, 3, 1, 0, "Resend 422"
                ),
            ],
        )

    assert alerted is True
    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content)
    assert body["to"] == [_CONFIG.recipient]  # the ops address, not the reader's (D-037)
    assert "1 of 2 digest sends failed" in body["text"]
    assert "b@example.com" in body["text"] and "Resend 422" in body["text"]


def test_digest_job_stays_silent_when_every_send_succeeded() -> None:
    with respx.mock:
        route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "a"}))
        alerted = alert_failed_digests(
            _CONFIG, [DigestSendResult("grid_power_software", "a@example.com", "sent", 1, 2, 0, 0)]
        )

    assert alerted is False
    assert route.call_count == 0


def test_digest_alert_never_raises_when_resend_is_the_thing_that_is_down() -> None:
    """Best-effort by nature — this is exactly why D-101 added Cloud Monitoring on top."""
    with respx.mock:
        respx.post(_RESEND).mock(return_value=httpx.Response(500, text="down"))
        alerted = alert_failed_digests(
            _CONFIG,
            [DigestSendResult("grid_power_software", "a@example.com", "failed", None, 0, 0, 0)],
        )

    assert alerted is False
