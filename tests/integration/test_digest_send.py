"""Integration tests for the send orchestrator (P3B2, P5.4 per-profile).

Real migrated SQLite; employers/postings/profiles/matches seeded directly; the verification gate
faked and Resend stubbed by respx — no network, no real email. Pins: happy-path send writes a
`sent` row addressed to the profile's email with the right payload; a Resend error leaves a
`failed` row carrying the error; an empty digest sends nothing and writes no row; and a successful
send advances the next digest's window.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import unquote

import httpx
import pytest
import respx
from sqlalchemy import Engine, func, select

from vja.db.engine import begin
from vja.db.matches import save_match
from vja.db.profiles import Profile, active_profiles, upsert_profile
from vja.db.schema import digests, employers, postings, users
from vja.digest.assembly import build_digest
from vja.digest.send import DigestConfig, send_digest
from vja.digest.unsubscribe import parse_unsubscribe_token

_PASS = lambda _url: True  # noqa: E731  (tiny test stub; a def would be noisier)
_EMAIL = "me@example.com"
# `recipient` here is the ops/alert address; the digest goes to the profile's email (D-037).
_CONFIG = DigestConfig(
    api_key="re_test", sender="onboarding@resend.dev", recipient="ops@example.com"
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
) -> int:
    with begin(engine) as conn:
        result = conn.execute(
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
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


def _profile(
    engine: Engine, *, vertical: str = "grid_power_software", email: str = _EMAIL
) -> Profile:
    upsert_profile(
        engine, user_email=email, vertical=vertical, resume_text="resume", domain_vocabulary=[]
    )
    return next(p for p in active_profiles(engine, vertical) if p.user_email == email)


def _match(engine: Engine, posting_id: int, profile: Profile, *, score: int = 70) -> None:
    with begin(engine) as conn:
        save_match(
            conn,
            posting_id,
            profile.id,
            profile.resume_version,
            {"verdict": "yes", "score": score, "fits": "[]", "gaps": "[]", "rationale": "ok"},
            model="claude-sonnet-4-6",
            trigger="nightly",
            now=datetime.now(UTC),
        )


def _digest_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(digests)).mappings().all()]


@respx.mock
def test_successful_send_writes_sent_row_with_correct_payload(migrated_engine: Engine) -> None:
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "abc"}))
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    now = datetime(2026, 6, 17, tzinfo=UTC)
    a = _posting(migrated_engine, emp, "a", first_seen=now, apply_url="https://jobs/a")
    _match(migrated_engine, a, prof)

    result = send_digest(
        migrated_engine, "grid_power_software", prof, now=now, config=_CONFIG, verify=_PASS
    )

    assert result.status == "sent"
    assert result.recipient == _EMAIL
    assert (result.new, result.closed, result.quarantined) == (1, 0, 0)
    rows = _digest_rows(migrated_engine)
    assert len(rows) == 1
    assert rows[0]["status"] == "sent"
    assert rows[0]["sent_at"] == now
    assert rows[0]["recipient"] == _EMAIL  # the profile's email, not the ops address
    assert rows[0]["contents"]["new"][0]["external_id"] == "a"

    sent = json.loads(route.calls.last.request.content)
    assert sent["from"] == "onboarding@resend.dev"
    assert sent["to"] == [_EMAIL]  # addressed to the profile, not _CONFIG.recipient
    assert "1 new" in sent["subject"]
    assert route.calls.last.request.headers["Authorization"] == "Bearer re_test"


@respx.mock
def test_resend_error_leaves_a_failed_row(migrated_engine: Engine) -> None:
    respx.post(_RESEND).mock(return_value=httpx.Response(422, text="domain not verified"))
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    now = datetime(2026, 6, 17, tzinfo=UTC)
    a = _posting(migrated_engine, emp, "a", first_seen=now)
    _match(migrated_engine, a, prof)

    result = send_digest(
        migrated_engine, "grid_power_software", prof, now=now, config=_CONFIG, verify=_PASS
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
    prof = _profile(migrated_engine)
    now = datetime(2026, 6, 17, tzinfo=UTC)
    a = _posting(migrated_engine, emp, "a", first_seen=now)
    _match(migrated_engine, a, prof)

    result = send_digest(
        migrated_engine, "grid_power_software", prof, now=now, config=_CONFIG, verify=_PASS
    )

    assert result.status == "failed"
    assert _digest_rows(migrated_engine)[0]["status"] == "failed"


@respx.mock
def test_empty_digest_sends_nothing_and_writes_no_row(migrated_engine: Engine) -> None:
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200))
    _employer(migrated_engine)  # active employer but no matched postings → nothing changed
    prof = _profile(migrated_engine)

    result = send_digest(
        migrated_engine,
        "grid_power_software",
        prof,
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
    prof = _profile(migrated_engine)
    t1 = datetime(2026, 6, 16, tzinfo=UTC)
    old = _posting(migrated_engine, emp, "old", first_seen=t1 - timedelta(days=1))
    _match(migrated_engine, old, prof)

    # First send (baseline) ships "old" and stamps sent_at = t1.
    first = send_digest(
        migrated_engine, "grid_power_software", prof, now=t1, config=_CONFIG, verify=_PASS
    )
    assert first.status == "sent"

    # A posting that appears after the send must be the only "new" in the next build.
    fresh = _posting(migrated_engine, emp, "fresh", first_seen=t1 + timedelta(days=1))
    _match(migrated_engine, fresh, prof)
    contents = build_digest(migrated_engine, "grid_power_software", profile=prof, verify=_PASS)
    assert contents.since == t1
    assert {p.external_id for p in contents.new} == {"fresh"}


def _user(engine: Engine, *, email: str = _EMAIL, digest_paused: bool = False) -> int:
    with begin(engine) as conn:
        result = conn.execute(
            users.insert().values(
                google_sub=f"g-{email}",
                email=email,
                name="Me",
                created_at=datetime.now(UTC),
                digest_paused=digest_paused,
            )
        )
    pk = result.inserted_primary_key
    assert pk is not None
    return int(pk[0])


@respx.mock
def test_paused_user_sends_nothing_and_writes_no_row(migrated_engine: Engine) -> None:
    # D-094: the pause beats everything — even with matched postings ready to ship, nothing is
    # built, sent, or persisted (the check precedes build_digest, so no digests row / no window
    # advance; a future resume gets the accumulated diff).
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "abc"}))
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    _user(migrated_engine, digest_paused=True)
    now = datetime(2026, 6, 17, tzinfo=UTC)
    a = _posting(migrated_engine, emp, "a", first_seen=now)
    _match(migrated_engine, a, prof)

    result = send_digest(
        migrated_engine, "grid_power_software", prof, now=now, config=_CONFIG, verify=_PASS
    )

    assert result.status == "paused"
    assert result.digest_id is None
    assert not route.called
    with migrated_engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(digests)).scalar_one() == 0


@respx.mock
def test_send_carries_unsubscribe_footer_and_rfc8058_headers(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VJA_SESSION_SECRET", "integration-secret")
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "abc"}))
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    user_id = _user(migrated_engine)
    now = datetime(2026, 6, 17, tzinfo=UTC)
    a = _posting(migrated_engine, emp, "a", first_seen=now)
    _match(migrated_engine, a, prof)
    config = DigestConfig(
        api_key="re_test",
        sender="onboarding@resend.dev",
        recipient="ops@example.com",
        public_base_url="https://role-feed.com",
    )

    result = send_digest(
        migrated_engine, "grid_power_software", prof, now=now, config=config, verify=_PASS
    )

    assert result.status == "sent"
    sent = json.loads(route.calls.last.request.content)
    unsub = sent["headers"]["List-Unsubscribe"]
    assert unsub.startswith("<https://role-feed.com/unsubscribe?token=") and unsub.endswith(">")
    assert sent["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "https://role-feed.com/unsubscribe?token=" in sent["html"]
    assert "https://role-feed.com/unsubscribe?token=" in sent["text"]
    # Both product links ship together on the normal path (D-102).
    assert 'href="https://role-feed.com/dashboard"' in sent["html"]
    assert "https://role-feed.com/dashboard" in sent["text"]
    # The footer token authorizes exactly this user.
    token = unquote(unsub[1:-1].split("token=", 1)[1])
    claim = parse_unsubscribe_token(token)
    assert claim is not None and (claim.user_id, claim.email) == (user_id, _EMAIL)


@respx.mock
def test_send_without_users_row_omits_footer_but_keeps_the_dashboard_link(
    migrated_engine: Engine,
) -> None:
    # A pre-login seed profile has no users row → nothing to key a token on; send plain (D-094).
    # The dashboard link is not token-keyed, so it still ships (D-102) — that asymmetry is the
    # reason the two links are gated separately in `send_digest`.
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "abc"}))
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    now = datetime(2026, 6, 17, tzinfo=UTC)
    a = _posting(migrated_engine, emp, "a", first_seen=now)
    _match(migrated_engine, a, prof)
    config = DigestConfig(
        api_key="re_test",
        sender="onboarding@resend.dev",
        recipient="ops@example.com",
        public_base_url="https://role-feed.com",
    )

    result = send_digest(
        migrated_engine, "grid_power_software", prof, now=now, config=config, verify=_PASS
    )

    assert result.status == "sent"
    sent = json.loads(route.calls.last.request.content)
    assert "headers" not in sent
    assert "unsubscribe" not in sent["html"].lower()
    assert 'href="https://role-feed.com/dashboard"' in sent["html"]


@respx.mock
def test_send_without_public_base_url_omits_footer_headers_and_dashboard_link(
    migrated_engine: Engine,
) -> None:
    # Dev (no VJA_PUBLIC_BASE_URL): never render a relative/localhost link into a real email.
    route = respx.post(_RESEND).mock(return_value=httpx.Response(200, json={"id": "abc"}))
    emp = _employer(migrated_engine)
    prof = _profile(migrated_engine)
    _user(migrated_engine)
    now = datetime(2026, 6, 17, tzinfo=UTC)
    a = _posting(migrated_engine, emp, "a", first_seen=now)
    _match(migrated_engine, a, prof)

    result = send_digest(
        migrated_engine, "grid_power_software", prof, now=now, config=_CONFIG, verify=_PASS
    )

    assert result.status == "sent"
    sent = json.loads(route.calls.last.request.content)
    assert "headers" not in sent
    assert "unsubscribe" not in sent["html"].lower()
    assert "dashboard" not in sent["html"].lower()
    assert "dashboard" not in sent["text"].lower()
