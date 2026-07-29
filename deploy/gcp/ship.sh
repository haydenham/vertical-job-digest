#!/usr/bin/env bash
# Thin scripted redeploy for Rolefeed (Cloud Run service + two Jobs) — Phase A / D-066, D-103.
#
# One idempotent command that captures the CUTOVER.md flags so no deploy ever forgets
# `--platform linux/amd64`, a secret mount, or the Job image update. NOT full CI/CD (that's the
# deferred 9.6) — a thin wrapper over the exact flags CUTOVER §1/§5/§8 already proved.
#
# Scope: REDEPLOY of already-provisioned resources. The `rolefeed` service + the `vja-nightly` and
# `vja-digest` Jobs must already exist (stood up via deploy/gcp/CUTOVER.md §8). This script rebuilds
# the image at the current commit and rolls it onto all three. It does NOT migrate the schema
# (Alembic stays a deliberate manual step — CUTOVER §3), seed, touch the domain / OAuth redirect
# URIs, or create/retarget the Cloud Scheduler triggers (CUTOVER §8 owns the cadence).
#
# It also NEVER writes the *service's* prod guard env vars (VJA_AUTH_REQUIRED / VJA_COOKIE_SECURE /
# VJA_PUBLIC_BASE_URL, set once in CUTOVER §9): omitting --set-env-vars preserves them, so a
# redeploy can't silently reopen auth. The post-deploy 401 smoke assertion is the tripwire if it ever
# regresses. (The nightly *Job* is the one exception: it gets VJA_PUBLIC_BASE_URL explicitly — the
# digest's unsubscribe links need the public origin, D-094 — which is additive, not a guard.)
#
# Usage:
#   ./deploy/gcp/ship.sh          # build → push → deploy service → update both Jobs → smoke
#   ./deploy/gcp/ship.sh --force  # skip the dirty-working-tree confirmation
#
# Requires: gcloud (authenticated, docker configured for Artifact Registry), docker, git. No secret
# VALUES live here — secrets are referenced by name only (Secret Manager mounts them at deploy).
set -euo pipefail

# --- Locked values (from CUTOVER.md §"Locked values" / 9.5c; overridable via env) --------------
: "${PROJECT_ID:=role-feed-prod}"
: "${REGION:=us-central1}"
: "${AR_REPO:=rolefeed}"
: "${SERVICE:=rolefeed}"
: "${JOB:=vja-nightly}"
: "${DIGEST_JOB:=vja-digest}"
: "${RUNTIME_SA:=850723734041-compute@developer.gserviceaccount.com}"

# D-103: the pipeline and the digest are two Jobs on two schedules. `vja-nightly` keeps its name
# (renaming a live Job means recreating it, repointing its Scheduler trigger and rewriting the
# alert policies, for no functional gain) but now runs every 4 HOURS with --no-digest; `vja-digest`
# sends once a morning. The pipeline timeout must sit BELOW the 4h interval — D-086's 6h was sized
# for a once-daily job and would let one hung run overlap the next three. 3h leaves ample headroom
# over a ~15-20 min steady-state run while still failing fast enough to matter.
: "${JOB_TASK_TIMEOUT_SECONDS:=10800}"
: "${JOB_ARGS:=--no-digest}"
: "${DIGEST_JOB_TASK_TIMEOUT_SECONDS:=3600}"

# D-086: the digest half is not delivery-idempotent across Cloud Run task attempts. A 2026-07-14
# execution hit the old 2h timeout after aviation emails had sent; maxRetries=1 restarted the whole
# process and sent aviation again before reaching grid. Zero retries therefore stays on BOTH jobs:
# mandatory on `vja-digest` (which sends), and kept on the pipeline for now because pairing
# automatic retries with the new skip-if-running guard (D-103) can wedge a run. A process-level
# failure is an operator-reviewed manual rerun.
: "${JOB_MAX_RETRIES:=0}"

# D-103 runaway guard: bounds ONE run's matching per profile, unset by default in code. At six runs
# a day an inflated candidate set gets six chances instead of one; overflow is deferred to the next
# run, never dropped. Deliberately NOT the D-057 daily ceiling, which refuses work outright and is
# keyed to signups (D-101 decoupled the two on purpose).
: "${PIPELINE_MAX_MATCHES:=400}"

# D-090: matching cut over only after the human-reviewed eight-case Sonnet/Luna comparison.
# `--update-env-vars` preserves the auth/cookie/public-URL guards while making the exact route and
# effort explicit on both Cloud Run targets; rollback remains a route change or prior revision.
: "${MATCH_MODEL_ROUTE:=openai/gpt-5.6-luna}"
: "${MATCH_REASONING_EFFORT:=low}"
LAYER2_ENV="VJA_MATCH_MODEL=${MATCH_MODEL_ROUTE},VJA_MATCH_EFFORT=${MATCH_REASONING_EFFORT}"

# D-101: the signup-backfill spend ceiling, set explicitly for the public launch. The code default
# (5.0) is sized for a dev machine; at ~$0.01/match proxy × the 100-posting backfill cap it is ~5
# signups/day, which a launch day clears before lunch — and the refusal lands on a new user at
# onboarding as a 429. $25 ≈ 25 signup backfills/day (~$5-6 real spend, the proxy runs ~5x
# conservative) and is the abuse guard on a public signup flow. Service only: the ceiling is read at
# POST /api/profiles, never by the nightly (which D-101 also removed from the count).
: "${DAILY_LLM_BUDGET_USD:=25}"
SERVICE_ENV="${LAYER2_ENV},VJA_DAILY_LLM_BUDGET_USD=${DAILY_LLM_BUDGET_USD}"

# Unattended CD (9.6/D-068) sets this to 1: on a failed smoke, auto-roll traffic back to the prior
# revision before exiting non-zero (gcloud run deploy sends 100% traffic to the new revision on deploy,
# so a bad revision is already serving). Default 0 = the manual behavior — print rollback + exit, human
# is watching.
: "${ROLLBACK_ON_SMOKE_FAIL:=0}"

# ⚠ --set-secrets has REPLACE semantics: each list below is the COMPLETE set mounted on that target.
# Adding a secret to prod means adding it here too, or the next deploy drops it. Kept identical to
# CUTOVER §5 (service, 9) and §8 (job, 7 — VJA_SESSION_SECRET signs unsubscribe tokens, D-094).
SERVICE_SECRETS="ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest,RESEND_API_KEY=RESEND_API_KEY:latest,VJA_DATABASE_URL=VJA_DATABASE_URL:latest,VJA_SESSION_SECRET=VJA_SESSION_SECRET:latest,GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID:latest,GOOGLE_CLIENT_SECRET=GOOGLE_CLIENT_SECRET:latest,VJA_DIGEST_FROM=VJA_DIGEST_FROM:latest,VJA_DIGEST_RECIPIENT=VJA_DIGEST_RECIPIENT:latest"
JOB_SECRETS="ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest,RESEND_API_KEY=RESEND_API_KEY:latest,VJA_DATABASE_URL=VJA_DATABASE_URL:latest,VJA_DIGEST_FROM=VJA_DIGEST_FROM:latest,VJA_DIGEST_RECIPIENT=VJA_DIGEST_RECIPIENT:latest,VJA_SESSION_SECRET=VJA_SESSION_SECRET:latest"

# D-094: the nightly composer signs each digest's unsubscribe token with VJA_SESSION_SECRET (mounted
# above — same secret the API verifies with) and builds the absolute link off the public origin. The
# Job needs the env var explicitly; the *service* keeps its CUTOVER §9 guard policy (never written
# here — see header comment).
JOB_ENV="${LAYER2_ENV},VJA_PUBLIC_BASE_URL=${VJA_PUBLIC_BASE_URL:-https://role-feed.com}"
PIPELINE_JOB_ENV="${JOB_ENV},VJA_PIPELINE_MAX_MATCHES=${PIPELINE_MAX_MATCHES}"

FORCE=0
[[ "${1:-}" == "--force" || "${1:-}" == "-y" ]] && FORCE=1

# --- Preflight ---------------------------------------------------------------------------------
for cmd in gcloud docker git; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "error: '$cmd' not found on PATH." >&2; exit 1; }
done

# Repo root = two levels up from this script (deploy/gcp/ship.sh). Build context + git run there.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

SHA="$(git rev-parse --short HEAD)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${SERVICE}:${SHA}"

# The image tag is the short SHA — a dirty tree ships a tag that doesn't match committed code.
if [[ -n "$(git status --porcelain)" && "$FORCE" -ne 1 ]]; then
  echo "warning: working tree is dirty — image tag '$SHA' won't match the committed code." >&2
  read -r -p "Deploy anyway? [y/N] " reply
  [[ "$reply" == "y" || "$reply" == "Y" ]] || { echo "aborted."; exit 1; }
fi

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud config set run/region "$REGION" >/dev/null

echo "==> Deploying $IMAGE"
echo "    project=$PROJECT_ID region=$REGION service=$SERVICE jobs=$JOB,$DIGEST_JOB"

# --- 1+2. Build + push (⚠ --platform linux/amd64 is mandatory: arm64 laptop → amd64 Cloud Run) ---
echo "==> [1/6] docker build --platform linux/amd64"
docker build --platform linux/amd64 -t "$IMAGE" .
echo "==> [2/6] docker push"
docker push "$IMAGE"

# --- 3. Capture the current serving revision BEFORE deploying, for one-command rollback ----------
PREV="$(gcloud run services describe "$SERVICE" --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)"
echo "==> [3/6] prior serving revision: ${PREV:-<none>}"

# --- 4. Deploy the service (re-asserts the full CUTOVER §5 config; NO --set-env-vars → guards kept)
echo "==> [4/6] deploy service $SERVICE"
# --no-cpu-throttling (D-101) is load-bearing, not a performance tweak: the signup flow returns 202
# and finishes `run_backfill` in a FastAPI BackgroundTask, i.e. OUTSIDE a request. Under Cloud Run's
# default throttling that work only gets CPU when another request happens to land on the same
# instance, so a backfill's progress depended on the dashboard's own 10s poll — and a real user's
# 2026-07-24 backfill stamped `backfill_started_at` and never completed. Reasserted on every deploy,
# like --task-timeout on the Job. (This removes throttling, not instance death: Cloud Run cannot see
# background work when scaling down. The durable fix is moving the backfill off the request path.)
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --allow-unauthenticated \
  --service-account "$RUNTIME_SA" \
  --no-cpu-throttling \
  --update-env-vars "$SERVICE_ENV" \
  --set-secrets "$SERVICE_SECRETS"

# --- 5. Update both Jobs to the same image (D-031 trigger-swap: one image, three run targets) ----
# `--args` is asserted on the PIPELINE Job only: it is what separates the two halves of the D-103
# split, and dropping it there would silently start sending digests six times a day. The digest Job
# deliberately carries no `--args` (it exists to send), and that absence is pinned by
# `test_pipeline_job_never_ships_without_the_no_digest_flag` — so this asymmetry is the contract,
# not an oversight. NB `gcloud run jobs update` has no `--clear-args`, so the digest Job's args
# cannot be reset from here; if one were ever set manually, clear it in the console.
#
# ⚠ `--args=` MUST use the equals form. `--args "--no-digest"` fails in gcloud's own argument parser
# ("argument --args: expected one argument") because the value starts with a dash and argparse reads
# it as the next flag. This broke a CD run on 2026-07-29; it is not cosmetic style.
echo "==> [5/6] update pipeline job $JOB (every 4h, --no-digest)"
gcloud run jobs update "$JOB" \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --args="$JOB_ARGS" \
  --task-timeout "$JOB_TASK_TIMEOUT_SECONDS" \
  --max-retries "$JOB_MAX_RETRIES" \
  --update-env-vars "$PIPELINE_JOB_ENV" \
  --set-secrets "$JOB_SECRETS"

echo "==> [6/6] update digest job $DIGEST_JOB (daily)"
gcloud run jobs update "$DIGEST_JOB" \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --task-timeout "$DIGEST_JOB_TASK_TIMEOUT_SECONDS" \
  --max-retries "$JOB_MAX_RETRIES" \
  --update-env-vars "$JOB_ENV" \
  --set-secrets "$JOB_SECRETS"

# --- Smoke -------------------------------------------------------------------------------------
URL="$(gcloud run services describe "$SERVICE" --format='value(status.url)')"
REVISION="$(gcloud run services describe "$SERVICE" --format='value(status.latestReadyRevisionName)')"
echo "==> Smoke ($URL)"

# A failed smoke means the just-deployed revision is bad but already serving 100% of traffic. Under
# ROLLBACK_ON_SMOKE_FAIL=1 (CD), shift traffic back to the prior revision before failing; otherwise just
# fail (the manual path prints the rollback command below and a human runs it).
smoke_fail() {
  echo "    $1" >&2
  if [[ "$ROLLBACK_ON_SMOKE_FAIL" == "1" && -n "$PREV" && "$PREV" != "$REVISION" ]]; then
    echo "==> smoke failed — auto-rolling traffic back to $PREV" >&2
    gcloud run services update-traffic "$SERVICE" --region "$REGION" --to-revisions="$PREV=100" >&2 \
      || echo "    auto-rollback FAILED — roll back manually: gcloud run services update-traffic $SERVICE --region $REGION --to-revisions=$PREV=100" >&2
  fi
  exit 1
}

health="$(curl -fsS "$URL/api/health" || true)"
if [[ "$health" == *'"status":"ok"'* ]]; then
  echo "    health: ok"
else
  smoke_fail "health: FAILED (got: ${health:-<no response>})"
fi

# Auth guard must have survived the redeploy: anon request to a real vertical → 401 (D-055/D-067).
# NB: /api/postings needs the `vertical` param or FastAPI returns 422 (validation before auth).
code="$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/postings?vertical=grid_power_software")"
if [[ "$code" == "401" ]]; then
  echo "    auth guard: ok (anon → 401)"
else
  smoke_fail "auth guard: FAILED (expected 401, got $code) — VJA_AUTH_REQUIRED may have regressed"
fi

echo
echo "==> Deployed revision: $REVISION"
if [[ -n "$PREV" && "$PREV" != "$REVISION" ]]; then
  echo "    rollback:  gcloud run services update-traffic $SERVICE --region $REGION --to-revisions=$PREV=100"
fi
echo "done."
