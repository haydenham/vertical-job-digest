"""Integration tests for the nightly orchestrator (P3B3, P5.4 compose extract→match→send).

Real migrated SQLite; fetchers faked via the injected `resolve_fetcher` (as in
`tests/system/test_run_pipeline.py`); the Layer-2 LLM pass faked via the injected `run_layer2`
(so no Anthropic client is constructed); Resend stubbed by respx; verification faked. Pins the
composition contracts: a happy run extracts+matches, sends the per-profile digest with rationale
and does NOT alert; the LLM totals land on the run row; a failed digest send flips the run to
`failed` and fires an alert email; a pipeline failure alerts even when the digest skips; an empty
universe sends nothing.
"""

import json
from datetime import UTC, datetime

import httpx
import respx
from sqlalchemy import Engine, select

from vja.db.engine import begin
from vja.db.matches import save_match
from vja.db.profiles import active_profiles, upsert_profile
from vja.db.schema import employers, pipeline_runs, postings
from vja.digest.send import DigestConfig
from vja.fetchers.base import FetchError
from vja.models import AtsType, Employer, RawPosting
from vja.nightly import Layer2Summary, run_nightly

_PASS = lambda _url: True  # noqa: E731  (tiny test stub)
_EMAIL = "me@example.com"
_CONFIG = DigestConfig(
    api_key="re_test", sender="onboarding@resend.dev", recipient="ops@example.com"
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


def _fake_layer2(engine: Engine, vertical: str, *, client: object, now: datetime) -> Layer2Summary:
    """Stand in for extraction+matching: write a relevant match for every unmatched open posting.

    Mirrors what the real Layer-2 pass yields (a `matches` row per surviving posting), without an
    Anthropic call — so the digest has rationale to render and the run records non-zero LLM totals.
    """
    open_ids_stmt = (
        select(postings.c.id)
        .select_from(postings.join(employers, postings.c.employer_id == employers.c.id))
        .where(employers.c.vertical == vertical, postings.c.status == "open")
    )
    with engine.connect() as conn:
        open_ids = [row[0] for row in conn.execute(open_ids_stmt).all()]

    matched = 0
    for profile in active_profiles(engine, vertical):
        for posting_id in open_ids:
            with begin(engine) as conn:
                save_match(
                    conn,
                    posting_id,
                    profile.id,
                    profile.resume_version,
                    {"verdict": "yes", "score": 80, "fits": "[]", "gaps": "[]", "rationale": "fit"},
                    model="claude-sonnet-4-6",
                    trigger="nightly",
                    now=now,
                )
            matched += 1
    return Layer2Summary(extracted=matched, matched=matched, est_cost_usd=0.01 * matched)


def _profile(engine: Engine) -> None:
    upsert_profile(
        engine,
        user_email=_EMAIL,
        vertical="grid_power_software",
        resume_text="resume",
        domain_vocabulary=[],
    )


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
    _profile(migrated_engine)

    result = run_nightly(
        migrated_engine,
        now=_NOW,
        config=_CONFIG,
        resolve_fetcher=_resolver(FakeFetcher({eid: [_posting("p1")]})),
        verify=_PASS,
        run_layer2=_fake_layer2,
    )

    assert result.status == "ok"
    assert result.alerted is False
    assert result.run.postings_new == 1
    assert [d.status for d in result.digests] == ["sent"]
    assert [d.recipient for d in result.digests] == [_EMAIL]  # addressed to the profile (D-027)
    assert (result.extraction_calls, result.match_calls) == (1, 1)
    assert route.call_count == 1  # the digest only — no alert

    # The digest body carries the rationale, and the run row records the LLM totals.
    body = json.loads(route.calls.last.request.content)
    assert "yes" in body["text"] and "80" in body["text"]
    with migrated_engine.connect() as conn:
        run_row = conn.execute(select(pipeline_runs)).mappings().one()
    assert run_row["match_calls"] == 1
    assert run_row["llm_cost_usd"] == 0.01


@respx.mock
def test_failed_digest_send_flips_to_failed_and_alerts(migrated_engine: Engine) -> None:
    # First POST (digest) is rejected; second POST (alert) succeeds.
    route = respx.post(_RESEND).mock(
        side_effect=[httpx.Response(422, text="domain not verified"), httpx.Response(200)]
    )
    eid = _seed(migrated_engine)
    _profile(migrated_engine)

    result = run_nightly(
        migrated_engine,
        now=_NOW,
        config=_CONFIG,
        resolve_fetcher=_resolver(FakeFetcher({eid: [_posting("p1")]})),
        verify=_PASS,
        run_layer2=_fake_layer2,
    )

    assert result.status == "failed"
    assert result.alerted is True
    assert route.call_count == 2  # failed digest + alert
    assert "FAILED" in json.loads(route.calls.last.request.content)["subject"]


@respx.mock
def test_pipeline_failure_alerts_even_when_digest_skips(migrated_engine: Engine) -> None:
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "alert"}))
    eid = _seed(migrated_engine)
    _profile(migrated_engine)

    result = run_nightly(
        migrated_engine,
        now=_NOW,
        config=_CONFIG,
        resolve_fetcher=_resolver(FakeFetcher({eid: FetchError("outage")})),
        verify=_PASS,
        run_layer2=_fake_layer2,
    )

    assert result.run.status == "failed"
    assert result.status == "failed"
    assert result.alerted is True
    # No postings → no matches → digest empty → skipped (D-028); the lone Resend call is the alert.
    assert [d.status for d in result.digests] == ["skipped"]
    assert route.call_count == 1
    assert "FAILED" in json.loads(route.calls.last.request.content)["subject"]


@respx.mock
def test_empty_universe_sends_nothing(migrated_engine: Engine) -> None:
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200))
    eid = _seed(migrated_engine)
    _profile(migrated_engine)

    result = run_nightly(
        migrated_engine,
        now=_NOW,
        config=_CONFIG,
        resolve_fetcher=_resolver(FakeFetcher({eid: []})),
        verify=_PASS,
        run_layer2=_fake_layer2,
    )

    assert result.status == "ok"
    assert result.alerted is False
    assert [d.status for d in result.digests] == ["skipped"]
    assert not route.called
