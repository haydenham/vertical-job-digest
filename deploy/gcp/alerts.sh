#!/usr/bin/env bash
# Job alerting for Rolefeed (D-101, extended by D-103) — the D-094 kept beta-exit minimum.
#
# Before this script the project had ZERO alert policies and ZERO notification channels: if a Job
# failed or the Scheduler never fired it, nobody found out. The in-process hard-failure email
# (D-037) cannot help — it needs the process to be running to send anything.
#
# TWO policies PER JOB, all wired to one email channel:
#   A. "<job> execution failed"  — any failed task attempt in a 10-minute window.
#   B. "<job> did not run"       — no successful task attempt within that job's absence window (the
#                                  Job's own metric only emits points around an execution, so the
#                                  absence of points IS the did-not-run signal).
#
# Since D-103 there are two jobs on two cadences, so each gets its OWN absence window — a single
# shared window cannot serve both:
#   vja-nightly  every 4h  → 5h   (one missed trigger is a real signal; 4h cadence + ~1h slack)
#   vja-digest   daily     → 26h  (unchanged from D-101's nightly reasoning)
#
# Policy B is a PromQL condition, and that is not a stylistic choice. The obvious implementation is
# a `conditionAbsent`, and it CANNOT express the daily case: the API caps absence duration at 23h30m
# ("Durations longer than 23h30m are not supported" — observed, not guessed), while successive daily
# runs are ~24h apart. Any absence window short enough to be legal is shorter than the normal gap
# between runs, so the policy would fire every single day. The window also has to tolerate real
# drift: the metric is written at task *completion* and run duration varies, so observed completions
# spread across a ~1.5h band even though the Scheduler fires on the hour exactly.
# `absent_over_time(...[26h])` states the requirement directly and has no such cap. PromQL is kept
# for the 4-hourly job too, for one code path. A flapping alert is worse than no alert — it trains
# you to ignore the one that matters.
#
# Deliberately uses the Monitoring REST API over `curl` rather than `gcloud alpha monitoring`: the
# alpha component is not installed, and an ops script should not require a component install to run.
#
# JSON bodies are built by python heredocs reading their inputs from the ENVIRONMENT, never from
# interpolated shell strings: the policy documentation contains backticks, quotes and newlines, all
# of which the shell would otherwise try to interpret.
#
# Idempotent: every object is looked up by displayName and created only when absent, so re-running
# is a no-op. Change a policy by deleting it in the console and re-running.
#
# Usage:
#   ./deploy/gcp/alerts.sh            # create anything missing, then list what exists
#   OPS_EMAIL=you@example.com ./deploy/gcp/alerts.sh
#
# NOTE: a newly created email channel is UNVERIFIED until the recipient clicks Google's
# verification link. An unverified channel does not deliver. Check your inbox after the first run.
set -euo pipefail

: "${PROJECT_ID:=role-feed-prod}"
: "${OPS_EMAIL:=haydenham10@gmail.com}"
: "${CHANNEL_NAME:=rolefeed-ops}"
# "<job>:<PromQL absence lookback>:<what the job does>" — see header for how each window is chosen.
: "${JOB_SPECS:=vja-nightly:5h:the 4-hourly fetch/diff/extract/match pipeline (D-103)
vja-digest:26h:the daily digest send}"

export PROJECT_ID OPS_EMAIL CHANNEL_NAME

API="https://monitoring.googleapis.com/v3/projects/${PROJECT_ID}"

for cmd in gcloud curl python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "error: '$cmd' not found on PATH." >&2; exit 1; }
done

TOKEN="$(gcloud auth print-access-token)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export WORK

api_get() { curl -sS -H "Authorization: Bearer $TOKEN" "$API/$1"; }

# api_post <collection> <body-file> — prints the created resource's `name`, or reports and exits.
api_post() {
  curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d @"$2" "$API/$1" >"$WORK/response.json"
  COLLECTION="$1" python3 <<'PY'
import json, os, sys

with open(os.path.join(os.environ["WORK"], "response.json")) as fh:
    body = json.load(fh)
if "error" in body:
    print(f"error creating {os.environ['COLLECTION']}:", file=sys.stderr)
    print("   ", body["error"].get("message"), file=sys.stderr)
    sys.exit(1)
print(body["name"])
PY
}

# find_by_display_name <collection> <displayName> — prints the resource `name`, or nothing.
find_by_display_name() {
  api_get "$1" >"$WORK/list.json"
  COLLECTION="$1" WANTED="$2" python3 <<'PY'
import json, os

collection = os.environ["COLLECTION"]
with open(os.path.join(os.environ["WORK"], "list.json")) as fh:
    data = json.load(fh)
for item in data.get(collection, []):
    if item.get("displayName") == os.environ["WANTED"]:
        print(item["name"])
        break
PY
}

echo "==> project=$PROJECT_ID"

# --- 1. Notification channel -------------------------------------------------------------------
CHANNEL="$(find_by_display_name notificationChannels "$CHANNEL_NAME")"
if [[ -n "$CHANNEL" ]]; then
  echo "==> [1] channel exists: $CHANNEL"
else
  echo "==> [1] creating email channel '$CHANNEL_NAME' → $OPS_EMAIL"
  python3 <<'PY'
import json, os

body = {
    "type": "email",
    "displayName": os.environ["CHANNEL_NAME"],
    "description": "Rolefeed ops alerts (D-101). Created by deploy/gcp/alerts.sh.",
    "labels": {"email_address": os.environ["OPS_EMAIL"]},
    "enabled": True,
}
with open(os.path.join(os.environ["WORK"], "channel.json"), "w") as fh:
    json.dump(body, fh)
PY
  CHANNEL="$(api_post notificationChannels "$WORK/channel.json")"
  echo "    created: $CHANNEL"
  echo "    ! verify it: Google just emailed $OPS_EMAIL a confirmation link. Until it is clicked,"
  echo "      this channel delivers nothing."
fi
export CHANNEL

# --- 2. Per-job policy pair ----------------------------------------------------------------------
# One loop over JOB_SPECS, so adding a scheduled Job is a one-line spec, not a copied block.
while IFS=: read -r JOB ABSENCE_WINDOW JOB_ROLE; do
  [[ -z "$JOB" ]] && continue
  export JOB ABSENCE_WINDOW JOB_ROLE
  echo "==> [$JOB] absence window=$ABSENCE_WINDOW — $JOB_ROLE"

# --- 2a. Policy A — execution failed --------------------------------------------------------------
POLICY_A_NAME="${JOB} execution failed"
export POLICY_A_NAME
if [[ -n "$(find_by_display_name alertPolicies "$POLICY_A_NAME")" ]]; then
  echo "    policy exists: $POLICY_A_NAME"
else
  echo "    creating policy: $POLICY_A_NAME"
  python3 <<'PY'
import json, os

job = os.environ["JOB"]
role = os.environ["JOB_ROLE"]
base = (
    'metric.type="run.googleapis.com/job/completed_task_attempt_count"'
    ' AND resource.type="cloud_run_job"'
    f' AND resource.label."job_name"="{job}"'
)
doc = (
    f"A **{job}** task attempt failed — that is {role}.\n\n"
    "The Job runs with `--max-retries 0` on purpose (D-086/D-103): the digest half is not "
    "delivery-idempotent across task attempts, so an automatic retry could send a vertical its "
    "digest twice. Read the logs, then rerun it manually:\n\n"
    f"    gcloud run jobs executions list --job={job} --region=us-central1\n"
    f"    gcloud run jobs execute {job} --region=us-central1\n"
)
body = {
    "displayName": os.environ["POLICY_A_NAME"],
    "combiner": "OR",
    "enabled": True,
    "notificationChannels": [os.environ["CHANNEL"]],
    "documentation": {"mimeType": "text/markdown", "content": doc},
    "conditions": [
        {
            "displayName": "failed task attempts > 0",
            "conditionThreshold": {
                "filter": base + ' AND metric.label."result"="failed"',
                "aggregations": [
                    {
                        "alignmentPeriod": "600s",
                        "perSeriesAligner": "ALIGN_SUM",
                        "crossSeriesReducer": "REDUCE_SUM",
                    }
                ],
                "comparison": "COMPARISON_GT",
                "thresholdValue": 0,
                "duration": "0s",
                "trigger": {"count": 1},
            },
        }
    ],
}
with open(os.path.join(os.environ["WORK"], "policy_a.json"), "w") as fh:
    json.dump(body, fh)
PY
  api_post alertPolicies "$WORK/policy_a.json" >/dev/null
  echo "    created."
fi

# --- 2b. Policy B — did not run -------------------------------------------------------------------
POLICY_B_NAME="${JOB} did not run"
export POLICY_B_NAME
if [[ -n "$(find_by_display_name alertPolicies "$POLICY_B_NAME")" ]]; then
  echo "    policy exists: $POLICY_B_NAME"
else
  echo "    creating policy: $POLICY_B_NAME (absent_over_time $ABSENCE_WINDOW)"
  python3 <<'PY'
import json, os

job = os.environ["JOB"]
role = os.environ["JOB_ROLE"]
window = os.environ["ABSENCE_WINDOW"]
query = (
    "absent_over_time(run_googleapis_com:job_completed_task_attempt_count"
    f'{{job_name="{job}",result="succeeded"}}[{window}])'
)
doc = (
    f"No **{job}** task has succeeded in over {window}, so {role} has silently stopped. Nothing "
    "else would have told you: the in-process failure email (D-037) needs the process to be "
    "running to send anything.\n\n"
    "Check, in order: that the Cloud Scheduler trigger fired "
    f"(`gcloud scheduler jobs describe {job}-trigger --location=us-central1`), that the Job "
    "exists and is not stuck, then read the logs of the last execution.\n"
)
body = {
    "displayName": os.environ["POLICY_B_NAME"],
    "combiner": "OR",
    "enabled": True,
    "notificationChannels": [os.environ["CHANNEL"]],
    "documentation": {"mimeType": "text/markdown", "content": doc},
    "conditions": [
        {
            "displayName": f"no successful task attempt in {window}",
            "conditionPrometheusQueryLanguage": {
                "query": query,
                # The lookback IS the patience; once the query is true the situation is already a
                # missed run, so there is nothing to wait out.
                "duration": "0s",
                "evaluationInterval": "600s",
            },
        }
    ],
}
with open(os.path.join(os.environ["WORK"], "policy_b.json"), "w") as fh:
    json.dump(body, fh)
PY
  api_post alertPolicies "$WORK/policy_b.json" >/dev/null
  echo "    created."
fi

done <<< "$JOB_SPECS"

# --- Verify --------------------------------------------------------------------------------------
echo
echo "==> Alert policies now in $PROJECT_ID:"
api_get alertPolicies >"$WORK/policies.json"
api_get notificationChannels >"$WORK/channels.json"
python3 <<'PY'
import json, os

work = os.environ["WORK"]
with open(os.path.join(work, "policies.json")) as fh:
    for p in json.load(fh).get("alertPolicies", []):
        print(f"    {p['displayName']}  (enabled={p.get('enabled')})")
print("==> Notification channels:")
with open(os.path.join(work, "channels.json")) as fh:
    for c in json.load(fh).get("notificationChannels", []):
        email = c.get("labels", {}).get("email_address", "")
        print(f"    {c['displayName']}  {email}  [{c.get('verificationStatus', 'UNKNOWN')}]")
PY
echo "done."
