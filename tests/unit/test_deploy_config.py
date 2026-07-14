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
