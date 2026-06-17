"""Integration tests for the nightly orchestrator (P3B3).

Real migrated SQLite; fetchers faked via the injected `resolve_fetcher` (as in
`tests/system/test_run_pipeline.py`); Resend stubbed by respx; verification faked. Pins the
composition contracts: happy run sends the digest and does NOT alert; a failed digest send
flips the run to `failed` and fires an alert email; a pipeline failure alerts even when the
digest skips; an empty universe sends nothing.
"""

import json
from datetime import UTC, datetime

import httpx
import respx
from sqlalchemy import Engine

from vja.db.engine import begin
from vja.db.schema import employers
from vja.digest.send import DigestConfig
from vja.fetchers.base import FetchError
from vja.models import AtsType, Employer, RawPosting
from vja.nightly import run_nightly

_PASS = lambda _url: True  # noqa: E731  (tiny test stub)
_CONFIG = DigestConfig(
    api_key="re_test", sender="onboarding@resend.dev", recipient="me@example.com"
)
_RESEND = "https://api.resend.com/emails"
_NOW = datetime(2026, 6, 17, tzinfo=UTC)


class FakeFetcher:
    ats_type = AtsType.GREENHOUSE

    def __init__(self, plan: dict[int, list[RawPosting] | Exception]) -> None:
        self._plan = plan

    def fetch(self, employer: Employer) -> list[RawPosting]:
        outcome = self._plan[employer.id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _resolver(fetcher: FakeFetcher):  # type: ignore[no-untyped-def]
    return lambda _ats: fetcher


def _posting(external_id: str) -> RawPosting:
    return RawPosting(
        external_id=external_id,
        title="Engineer",
        apply_url=f"https://jobs.example.com/{external_id}",
        location="Remote",
        updated_at=None,
        raw={"id": external_id},
        description="Build it.",
    )


def _seed(engine: Engine, name: str = "Camus", slug: str = "camus") -> int:
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical="grid_power_software",
                name=name,
                ats_type="greenhouse",
                ats_slug=slug,
                source="manual",
                status="active",
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


@respx.mock
def test_happy_path_sends_digest_and_does_not_alert(migrated_engine: Engine) -> None:
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "a"}))
    eid = _seed(migrated_engine)

    result = run_nightly(
        migrated_engine,
        now=_NOW,
        config=_CONFIG,
        resolve_fetcher=_resolver(FakeFetcher({eid: [_posting("p1")]})),
        verify=_PASS,
    )

    assert result.status == "ok"
    assert result.alerted is False
    assert result.run.postings_new == 1
    assert [d.status for d in result.digests] == ["sent"]
    assert route.call_count == 1  # the digest only — no alert


@respx.mock
def test_failed_digest_send_flips_to_failed_and_alerts(migrated_engine: Engine) -> None:
    # First POST (digest) is rejected; second POST (alert) succeeds.
    route = respx.post(_RESEND).mock(
        side_effect=[httpx.Response(422, text="domain not verified"), httpx.Response(200)]
    )
    eid = _seed(migrated_engine)

    result = run_nightly(
        migrated_engine,
        now=_NOW,
        config=_CONFIG,
        resolve_fetcher=_resolver(FakeFetcher({eid: [_posting("p1")]})),
        verify=_PASS,
    )

    assert result.status == "failed"
    assert result.alerted is True
    assert route.call_count == 2  # failed digest + alert
    assert "FAILED" in json.loads(route.calls.last.request.content)["subject"]


@respx.mock
def test_pipeline_failure_alerts_even_when_digest_skips(migrated_engine: Engine) -> None:
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "alert"}))
    eid = _seed(migrated_engine)

    result = run_nightly(
        migrated_engine,
        now=_NOW,
        config=_CONFIG,
        resolve_fetcher=_resolver(FakeFetcher({eid: FetchError("outage")})),
        verify=_PASS,
    )

    assert result.run.status == "failed"
    assert result.status == "failed"
    assert result.alerted is True
    # No postings persisted → digest is empty → skipped (D-028); the lone Resend call is the alert.
    assert [d.status for d in result.digests] == ["skipped"]
    assert route.call_count == 1
    assert "FAILED" in json.loads(route.calls.last.request.content)["subject"]


@respx.mock
def test_empty_universe_sends_nothing(migrated_engine: Engine) -> None:
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200))
    eid = _seed(migrated_engine)

    result = run_nightly(
        migrated_engine,
        now=_NOW,
        config=_CONFIG,
        resolve_fetcher=_resolver(FakeFetcher({eid: []})),
        verify=_PASS,
    )

    assert result.status == "ok"
    assert result.alerted is False
    assert [d.status for d in result.digests] == ["skipped"]
    assert not route.called
