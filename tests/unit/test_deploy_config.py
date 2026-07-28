"""Production deployment-policy contracts that must survive every ship (D-086)."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SHIP = _ROOT / "deploy" / "gcp" / "ship.sh"
_CUTOVER = _ROOT / "deploy" / "gcp" / "CUTOVER.md"


def test_nightly_job_disables_unsafe_whole_task_retry() -> None:
    script = _SHIP.read_text(encoding="utf-8")

    assert ': "${JOB_TASK_TIMEOUT_SECONDS:=21600}"' in script
    assert ': "${JOB_MAX_RETRIES:=0}"' in script
    assert '--task-timeout "$JOB_TASK_TIMEOUT_SECONDS"' in script
    assert '--max-retries "$JOB_MAX_RETRIES"' in script

    create_runbook = _CUTOVER.read_text(encoding="utf-8")
    assert "--task-timeout 21600" in create_runbook
    assert "--max-retries 0" in create_runbook


def test_luna_matching_route_and_secret_survive_every_deploy() -> None:
    script = _SHIP.read_text(encoding="utf-8")

    assert ': "${MATCH_MODEL_ROUTE:=openai/gpt-5.6-luna}"' in script
    assert ': "${MATCH_REASONING_EFFORT:=low}"' in script
    assert script.count("OPENAI_API_KEY=OPENAI_API_KEY:latest") == 2
    # Both targets extend LAYER2_ENV rather than replacing it (SERVICE_ENV / JOB_ENV), so the route
    # rides along whatever else each target needs.
    assert '--update-env-vars "$SERVICE_ENV"' in script
    assert '--update-env-vars "$JOB_ENV"' in script
    assert 'SERVICE_ENV="${LAYER2_ENV},' in script
    assert 'JOB_ENV="${LAYER2_ENV},' in script


def test_backfill_cost_and_cpu_guards_survive_every_deploy() -> None:
    """D-101: both launch guards are deploy config, so a redeploy must not quietly drop them.

    The ceiling refuses signup backfills once the day's estimated spend is gone — at the code
    default ($5) that is ~5 signups/day, which a public launch clears before lunch. And
    --no-cpu-throttling is what lets the post-202 background backfill get CPU at all.
    """
    script = _SHIP.read_text(encoding="utf-8")

    assert ': "${DAILY_LLM_BUDGET_USD:=25}"' in script
    assert "VJA_DAILY_LLM_BUDGET_USD=${DAILY_LLM_BUDGET_USD}" in script
    assert "--no-cpu-throttling" in script


def test_unsubscribe_token_config_survives_every_deploy() -> None:
    # D-094: the nightly composer must sign with the same secret the API verifies with, and needs
    # the public origin for absolute links. Both mounted on the Job by every deploy.
    script = _SHIP.read_text(encoding="utf-8")

    assert script.count("VJA_SESSION_SECRET=VJA_SESSION_SECRET:latest") == 2  # service AND job
    assert "VJA_PUBLIC_BASE_URL=${VJA_PUBLIC_BASE_URL:-https://role-feed.com}" in script

    create_runbook = _CUTOVER.read_text(encoding="utf-8")
    assert create_runbook.count("VJA_SESSION_SECRET=VJA_SESSION_SECRET:latest") == 2
