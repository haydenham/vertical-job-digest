"""Production deployment-policy contracts that must survive every ship (D-086)."""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SHIP = _ROOT / "deploy" / "gcp" / "ship.sh"
_CUTOVER = _ROOT / "deploy" / "gcp" / "CUTOVER.md"


def test_both_jobs_disable_unsafe_whole_task_retry() -> None:
    """D-086 survives the D-103 split: neither Job may automatically retry a whole task.

    Mandatory on `vja-digest`, which is the half that sends and is not delivery-idempotent across
    attempts; kept on the pipeline because pairing retries with the new skip-if-running guard can
    wedge a run. Both `--task-timeout` and `--max-retries` are asserted on both update calls.
    """
    script = _SHIP.read_text(encoding="utf-8")

    assert ': "${JOB_MAX_RETRIES:=0}"' in script
    assert script.count('--max-retries "$JOB_MAX_RETRIES"') == 2  # pipeline AND digest
    assert '--task-timeout "$JOB_TASK_TIMEOUT_SECONDS"' in script
    assert '--task-timeout "$DIGEST_JOB_TASK_TIMEOUT_SECONDS"' in script

    create_runbook = _CUTOVER.read_text(encoding="utf-8")
    assert "--max-retries 0" in create_runbook


def test_pipeline_task_timeout_stays_below_the_four_hour_interval() -> None:
    """D-103: a pipeline timeout at or above the cadence lets a hung run overlap the next ones.

    D-086's 6h was sized for a once-daily Job. At a 4-hourly trigger it would let one stuck
    execution run through the next three windows, which is exactly what the skip-if-running guard
    then has to paper over.
    """
    script = _SHIP.read_text(encoding="utf-8")

    timeout = int(re.search(r"JOB_TASK_TIMEOUT_SECONDS:=(\d+)", script).group(1))  # type: ignore[union-attr]
    assert timeout < 4 * 60 * 60

    digest_timeout = int(
        re.search(r"DIGEST_JOB_TASK_TIMEOUT_SECONDS:=(\d+)", script).group(1)  # type: ignore[union-attr]
    )
    assert 0 < digest_timeout <= 4 * 60 * 60


def test_pipeline_job_never_ships_without_the_no_digest_flag() -> None:
    """The flag IS the split (D-103). Dropping it sends every user six digests a day."""
    script = _SHIP.read_text(encoding="utf-8")

    assert ': "${JOB_ARGS:=--no-digest}"' in script
    # The digest Job must NOT carry it — that one exists to send.
    pipeline_block = script.split("update pipeline job")[1].split("update digest job")[0]
    assert '--args="$JOB_ARGS"' in pipeline_block
    assert "--args" not in script.split("update digest job")[1]


def test_args_flag_uses_the_equals_form_gcloud_actually_accepts() -> None:
    """Regression (2026-07-29): `--args "--no-digest"` fails, and it fails in CD, not locally.

    gcloud's own argument parser rejects it — "argument --args: expected one argument" — because
    the value starts with a dash and argparse consumes it as the next flag. Only `--args=VALUE`
    works. The original version of the test above asserted the *broken* spelling, so it passed
    while the deploy was unrunnable: it pinned that a flag was present, never that gcloud would
    take it. Both files that spell the flag out are checked here.
    """
    for path in (_SHIP, _CUTOVER):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("--args") and not stripped.startswith("--args="):
                raise AssertionError(f"{path.name}: `--args` needs the equals form — {stripped!r}")


def test_pipeline_runaway_match_cap_survives_every_deploy() -> None:
    """D-103: at six runs a day an inflated candidate set gets six chances instead of one."""
    script = _SHIP.read_text(encoding="utf-8")

    assert ': "${PIPELINE_MAX_MATCHES:=' in script
    assert "VJA_PIPELINE_MAX_MATCHES=${PIPELINE_MAX_MATCHES}" in script
    # Pipeline only: the digest Job runs no matching, so the knob would be noise there.
    assert '--update-env-vars "$PIPELINE_JOB_ENV"' in script


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

    # Three provisioning blocks since D-103: the service, the pipeline Job, and the digest Job. The
    # digest Job is the one that actually signs tokens; the pipeline Job carries the same mount so
    # `ship.sh` can hold one JOB_SECRETS list for both.
    create_runbook = _CUTOVER.read_text(encoding="utf-8")
    assert create_runbook.count("VJA_SESSION_SECRET=VJA_SESSION_SECRET:latest") == 3
