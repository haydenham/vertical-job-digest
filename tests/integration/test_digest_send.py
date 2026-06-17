"""Integration tests for the send orchestrator (P3B2).

Real migrated SQLite; employers/postings seeded directly; the verification gate faked and
Resend stubbed by respx — no network, no real email. Pins: happy-path send writes a `sent`
row with the right payload; a Resend error leaves a `failed` row carrying the error; an empty
digest sends nothing and writes no row; and a successful send advances the next digest's window.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import respx
from sqlalchemy import Engine, func, select

from vja.db.engine import begin
from vja.db.schema import digests, employers, postings
from vja.digest.assembly import build_digest
from vja.digest.send import DigestConfig, send_digest

_PASS = lambda _url: True  # noqa: E731  (tiny test stub; a def would be noisier)
_CONFIG = DigestConfig(
    api_key="re_test", sender="onboarding@resend.dev", recipient="me@example.com"
)
_RESEND = "https://api.resend.com/emails"


def _employer(engine: Engine, *, vertical: str = "grid_power_software", name: str = "Camus") -> int:
    now = datetime.now(UTC)
    with begin(engine) as conn:
        result = conn.execute(
            employers.insert().values(
                vertical=vertical,
                name=name,
                ats_type="greenhouse",
                ats_slug=name.lower(),
                source="manual",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _posting(
    engine: Engine,
    employer_id: int,
    external_id: str,
    *,
    first_seen: datetime,
    status: str = "open",
    closed_at: datetime | None = None,
    apply_url: str = "https://jobs.example.com/x",
) -> None:
    with begin(engine) as conn:
        conn.execute(
            postings.insert().values(
                employer_id=employer_id,
                external_id=external_id,
                content_hash=f"h-{external_id}",
                raw_payload={},
                apply_url=apply_url,
                title="Engineer",
                location="Remote",
                status=status,
                first_seen_at=first_seen,
                last_seen_at=first_seen,
                closed_at=closed_at,
            )
        )


def _digest_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(digests)).mappings().all()]


@respx.mock
def test_successful_send_writes_sent_row_with_correct_payload(migrated_engine: Engine) -> None:
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "abc"}))
    emp = _employer(migrated_engine)
    now = datetime(2026, 6, 17, tzinfo=UTC)
    _posting(migrated_engine, emp, "a", first_seen=now, apply_url="https://jobs/a")

    result = send_digest(
        migrated_engine, "grid_power_software", now=now, config=_CONFIG, verify=_PASS
    )

    assert result.status == "sent"
    assert (result.new, result.closed, result.quarantined) == (1, 0, 0)
    rows = _digest_rows(migrated_engine)
    assert len(rows) == 1
    assert rows[0]["status"] == "sent"
    assert rows[0]["sent_at"] == now
    assert rows[0]["recipient"] == "me@example.com"
    assert rows[0]["contents"]["new"][0]["external_id"] == "a"

    sent = json.loads(route.calls.last.request.content)
    assert sent["from"] == "onboarding@resend.dev"
    assert sent["to"] == ["me@example.com"]
    assert "1 new" in sent["subject"]
    assert route.calls.last.request.headers["Authorization"] == "Bearer re_test"


@respx.mock
def test_resend_error_leaves_a_failed_row(migrated_engine: Engine) -> None:
    respx.post(_RESEND).mock(return_value=httpx.Response(422, text="domain not verified"))
    emp = _employer(migrated_engine)
    now = datetime(2026, 6, 17, tzinfo=UTC)
    _posting(migrated_engine, emp, "a", first_seen=now)

    result = send_digest(
        migrated_engine, "grid_power_software", now=now, config=_CONFIG, verify=_PASS
    )

    assert result.status == "failed"
    assert result.error is not None and "422" in result.error
    rows = _digest_rows(migrated_engine)
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert rows[0]["sent_at"] is None
    assert "domain not verified" in rows[0]["error"]


@respx.mock
def test_transport_error_leaves_a_failed_row(migrated_engine: Engine) -> None:
    respx.post(_RESEND).mock(side_effect=httpx.ConnectError("boom"))
    emp = _employer(migrated_engine)
    now = datetime(2026, 6, 17, tzinfo=UTC)
    _posting(migrated_engine, emp, "a", first_seen=now)

    result = send_digest(
        migrated_engine, "grid_power_software", now=now, config=_CONFIG, verify=_PASS
    )

    assert result.status == "failed"
    assert _digest_rows(migrated_engine)[0]["status"] == "failed"


@respx.mock
def test_empty_digest_sends_nothing_and_writes_no_row(migrated_engine: Engine) -> None:
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200))
    _employer(migrated_engine)  # active employer but no postings → nothing changed

    result = send_digest(
        migrated_engine,
        "grid_power_software",
        now=datetime(2026, 6, 17, tzinfo=UTC),
        config=_CONFIG,
        verify=_PASS,
    )

    assert result.status == "skipped"
    assert result.digest_id is None
    assert not route.called
    with migrated_engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(digests)).scalar_one() == 0


@respx.mock
def test_successful_send_advances_the_window(migrated_engine: Engine) -> None:
    respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "abc"}))
    emp = _employer(migrated_engine)
    t1 = datetime(2026, 6, 16, tzinfo=UTC)
    _posting(migrated_engine, emp, "old", first_seen=t1 - timedelta(days=1))

    # First send (baseline) ships "old" and stamps sent_at = t1.
    first = send_digest(
        migrated_engine, "grid_power_software", now=t1, config=_CONFIG, verify=_PASS
    )
    assert first.status == "sent"

    # A posting that appears after the send must be the only "new" in the next build.
    _posting(migrated_engine, emp, "fresh", first_seen=t1 + timedelta(days=1))
    contents = build_digest(migrated_engine, "grid_power_software", verify=_PASS)
    assert contents.since == t1
    assert {p.external_id for p in contents.new} == {"fresh"}
