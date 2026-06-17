"""Opt-in end-to-end send (P3B2, docs/08 Level 4 — the proof-of-loop milestone).

Excluded from the default run; invoke with ``uv run pytest -m e2e``. Actually sends a real
email through Resend, so it's skipped unless `RESEND_API_KEY` (or `resend-api-key`) is set.
With the sandbox sender (`onboarding@resend.dev`, D-029) `VJA_DIGEST_RECIPIENT` must be your
own Resend account email. Run before a milestone, not per-commit.
"""

import os
from datetime import UTC, datetime

import pytest
from dotenv import load_dotenv
from sqlalchemy import Engine

from vja.db.engine import begin
from vja.db.schema import employers, postings
from vja.digest.send import load_config, send_digest

load_dotenv()

pytestmark = pytest.mark.e2e

_HAS_KEY = bool(os.environ.get("RESEND_API_KEY") or os.environ.get("resend-api-key"))  # noqa: SIM112
_HAS_RECIPIENT = bool(os.environ.get("VJA_DIGEST_RECIPIENT"))


@pytest.mark.skipif(
    not (_HAS_KEY and _HAS_RECIPIENT),
    reason="needs RESEND_API_KEY (or resend-api-key) + VJA_DIGEST_RECIPIENT",
)
def test_real_send_through_resend(migrated_engine: Engine) -> None:
    now = datetime.now(UTC)
    with begin(migrated_engine) as conn:
        pk = conn.execute(
            employers.insert().values(
                vertical="grid_power_software",
                name="E2E Sandbox Co",
                ats_type="greenhouse",
                ats_slug="e2e",
                source="manual",
                status="active",
                created_at=now,
                updated_at=now,
            )
        ).inserted_primary_key
        assert pk is not None
        emp = pk[0]
        conn.execute(
            postings.insert().values(
                employer_id=emp,
                external_id="e2e-1",
                content_hash="h-e2e-1",
                raw_payload={},
                # A reliably-resolvable link so the real D-008 gate passes.
                apply_url="https://example.com/",
                title="Grid Software Engineer (E2E test)",
                location="Remote, US",
                status="open",
                first_seen_at=now,
                last_seen_at=now,
            )
        )

    # Real config + real verification gate (no `verify` injected) + real Resend POST.
    result = send_digest(migrated_engine, "grid_power_software", now=now, config=load_config())

    assert result.status == "sent", result.error
    assert result.new == 1
