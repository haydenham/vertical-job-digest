"""Unit tests for the nightly failure alert (P3B3).

`_failure_summary` is a pure string builder (no DB/network); `_send_failure_alert` posts via Resend
(stubbed by respx) and must never raise — if the alert itself can't send, it returns False.
"""

import json

import httpx
import respx

from vja.digest.send import DigestConfig, DigestSendResult
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
        postings_closed=0,
        results=[],
        errors=[{"employer_id": 5, "name": "Beta", "error": "FetchError('outage')"}],
    )


def test_failure_summary_includes_pipeline_fetch_and_digest_detail() -> None:
    digest = DigestSendResult("grid_power_software", "failed", None, 0, 0, 0, "Resend 422")
    summary = _failure_summary(_run(), [digest])
    assert "status=failed" in summary
    assert "fetch_failures=2" in summary
    assert "Beta" in summary and "outage" in summary
    assert "digest [grid_power_software]: failed" in summary
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
