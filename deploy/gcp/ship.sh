#!/usr/bin/env bash
# Thin scripted redeploy for Rolefeed (Cloud Run service + nightly Job) — Phase A / D-066.
#
# One idempotent command that captures the CUTOVER.md flags so no deploy ever forgets
# `--platform linux/amd64`, a secret mount, or the Job image update. NOT full CI/CD (that's the
# deferred 9.6) — a thin wrapper over the exact flags CUTOVER §1/§5/§8 already proved.
#
# Scope: REDEPLOY of already-provisioned resources. The `rolefeed` service + `vja-nightly` Job must
# already exist (stood up via deploy/gcp/CUTOVER.md). This script rebuilds the image at the current
# commit and rolls it onto both. It does NOT migrate the schema (Alembic stays a deliberate manual
# step — CUTOVER §3), seed, or touch the domain / OAuth redirect URIs.
#
# It also NEVER writes the *service's* prod guard env vars (VJA_AUTH_REQUIRED / VJA_COOKIE_SECURE /
# VJA_PUBLIC_BASE_URL, set once in CUTOVER §9): omitting --set-env-vars preserves them, so a
# redeploy can't silently reopen auth. The post-deploy 401 smoke assertion is the tripwire if it ever
# regresses. (The nightly *Job* is the one exception: it gets VJA_PUBLIC_BASE_URL explicitly — the
# digest's unsubscribe links need the public origin, D-094 — which is additive, not a guard.)
#
# Usage:
#   ./deploy/gcp/ship.sh          # build → push → deploy service → update Job → smoke
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
: "${RUNTIME_SA:=850723734041-compute@developer.gserviceaccount.com}"

# D-086: the nightly is not delivery-idempotent across Cloud Run task attempts. A 2026-07-14
# execution hit the old 2h timeout after aviation emails had sent; maxRetries=1 restarted the
# whole process and sent aviation again before reaching grid. Give the current sequential pipeline
# ample headroom and require an explicit operator rerun on process-level failure until durable
# per-execution delivery idempotency exists.
: "${JOB_TASK_TIMEOUT_SECONDS:=21600}"
: "${JOB_MAX_RETRIES:=0}"

# D-090: matching cut over only after the human-reviewed eight-case Sonnet/Luna comparison.
# `--update-env-vars` preserves the auth/cookie/public-URL guards while making the exact route and
# effort explicit on both Cloud Run targets; rollback remains a route change or prior revision.
: "${MATCH_MODEL_ROUTE:=openai/gpt-5.6-luna}"
: "${MATCH_REASONING_EFFORT:=low}"
LAYER2_ENV="VJA_MATCH_MODEL=${MATCH_MODEL_ROUTE},VJA_MATCH_EFFORT=${MATCH_REASONING_EFFORT}"

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
echo "    project=$PROJECT_ID region=$REGION service=$SERVICE job=$JOB"

# --- 1+2. Build + push (⚠ --platform linux/amd64 is mandatory: arm64 laptop → amd64 Cloud Run) ---
echo "==> [1/5] docker build --platform linux/amd64"
docker build --platform linux/amd64 -t "$IMAGE" .
echo "==> [2/5] docker push"
docker push "$IMAGE"

# --- 3. Capture the current serving revision BEFORE deploying, for one-command rollback ----------
PREV="$(gcloud run services describe "$SERVICE" --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)"
echo "==> [3/5] prior serving revision: ${PREV:-<none>}"

# --- 4. Deploy the service (re-asserts the full CUTOVER §5 config; NO --set-env-vars → guards kept)
echo "==> [4/5] deploy service $SERVICE"
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --allow-unauthenticated \
  --service-account "$RUNTIME_SA" \
  --update-env-vars "$LAYER2_ENV" \
  --set-secrets "$SERVICE_SECRETS"

# --- 5. Update the nightly Job to the same image (D-031 trigger-swap: one image, two run targets) -
echo "==> [5/5] update job $JOB"
gcloud run jobs update "$JOB" \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --task-timeout "$JOB_TASK_TIMEOUT_SECONDS" \
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
