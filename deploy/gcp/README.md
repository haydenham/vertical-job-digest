# Cloud provisioning runbook (Phase 9.5c — GCP + Neon + Cloudflare + Resend)

Stands up the cloud resources the **9.5d cutover** deploys *into*. This is the **9.5c** block: provision
only — **no app deploy, no schema migration, no go-live flips** (all 9.5d; see "Hand-off to 9.5d" below).
The scheduler/host is a swappable trigger (D-031/D-025): this directory is the cloud analogue of
`deploy/launchd/`, swapping the launchd trigger for Cloud Run, not changing app code.

Plan of record: `docs/12-cloud-deploy-plan.md` (locked decisions). Ledger: `docs/11` §3.

> **No secret values live in this file or the repo.** Secrets go to **GCP Secret Manager** (§5); the
> commands below reference them by name. The only place real values land is Secret Manager (prod) and a
> git-ignored local `.env` (for any local 9.5d step).

## Locked values (this deploy)

| Var | Value |
|---|---|
| `DOMAIN` | `role-feed.com` (Cloudflare Registrar; DNS stays on Cloudflare) |
| `PROJECT_ID` | `role-feed-prod` (must be globally unique — adjust if taken) |
| `REGION` | `us-central1` (GCP) |
| Neon region | **AWS us-east-2 (Ohio)** — nearest to us-central1 |
| `AR_REPO` | `rolefeed` (Artifact Registry Docker repo) |
| Sender | `digest@role-feed.com` (`VJA_DIGEST_FROM`) |

Paste this block into your shell before running the `gcloud` commands:

```sh
export PROJECT_ID=role-feed-prod
export REGION=us-central1
export AR_REPO=rolefeed
export DOMAIN=role-feed.com
```

---

## 1. Prereqs

```sh
gcloud --version                       # install: https://cloud.google.com/sdk/docs/install
gcloud auth login                      # run interactively (in this CLI: prefix with `! `)
gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"
```

`gcloud auth login` opens a browser — run it yourself (`! gcloud auth login`), it can't be driven headless.

## 2. Domain / DNS (Cloudflare)

`role-feed.com` is already registered on Cloudflare Registrar; **DNS stays on Cloudflare**. Nothing to add
here yet — Resend (§7) and the 9.5d custom-domain mapping each add their own records in their steps. Just
confirm the zone is active in the Cloudflare dashboard (Status: Active).

## 3. Neon Postgres (console)

Honors D-025 "cutover = a URL swap": fresh Neon DB, **no carryover** from local SQLite (the local data is
test data; postings re-fetch nightly).

1. https://console.neon.tech → **New Project**. Region **AWS US East 2 (Ohio)**. Name e.g. `rolefeed`.
2. Copy the **pooled** connection string (the `-pooler` host).
3. **Rewrite the scheme** for SQLAlchemy — it needs the `psycopg` (v3) driver (already a 9.1 dep):

   ```
   postgresql://user:pass@ep-xxx-pooler.us-east-2.aws.neon.tech/dbname?sslmode=require
   →  postgresql+psycopg://user:pass@ep-xxx-pooler.us-east-2.aws.neon.tech/dbname?sslmode=require
   ```

   This rewritten URL is `VJA_DATABASE_URL` → Secret Manager (§5).
4. **Reach test** (optional, no schema write) — confirm the URL connects before storing it:

   ```sh
   uv run python -c "import sqlalchemy as sa, os; sa.create_engine(os.environ['VJA_DATABASE_URL']).connect().close(); print('ok')"
   ```

   (Set `VJA_DATABASE_URL` in your shell first; don't commit it.) Schema (`alembic upgrade head`) is **9.5d**.

## 4. GCP project + APIs

```sh
gcloud projects create "$PROJECT_ID" --name="Rolefeed prod"   # or create in the console
# Link billing (console: Billing → link account, or):
gcloud billing projects link "$PROJECT_ID" --billing-account=XXXXXX-XXXXXX-XXXXXX

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com
```

No Cloud SQL API — Postgres is Neon.

## 5. Secret Manager

Create each secret, then add its value as a version. Replace `…` / pipe the real value; **do not** put
values in this file. Repeat the pattern per secret:

```sh
# one-time create (per name):
for s in ANTHROPIC_API_KEY OPENAI_API_KEY RESEND_API_KEY VJA_DATABASE_URL VJA_SESSION_SECRET \
         GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET VJA_DIGEST_FROM VJA_DIGEST_RECIPIENT; do
  gcloud secrets create "$s" --replication-policy=automatic
done

# add a version (example — reads value from stdin, nothing hits the shell history file):
printf '%s' "$VALUE" | gcloud secrets versions add VJA_DATABASE_URL --data-file=-
```

Values to load:

| Secret | Source |
|---|---|
| `ANTHROPIC_API_KEY` | existing (current LiteLLM Layer-2 default routes) |
| `OPENAI_API_KEY` | GPT-5.6 Terra (ready-but-off Layer-3 discovery Job) |
| `RESEND_API_KEY` | existing (digest + alert email) |
| `VJA_DATABASE_URL` | Neon, `+psycopg` rewritten (§3) |
| `VJA_SESSION_SECRET` | `openssl rand -hex 32` (fresh for prod) |
| `GOOGLE_CLIENT_ID` | OAuth web client (§6) |
| `GOOGLE_CLIENT_SECRET` | OAuth web client (§6) |
| `VJA_DIGEST_FROM` | `digest@role-feed.com` |
| `VJA_DIGEST_RECIPIENT` | ops/alert address (NOT the digest recipient — that's the profile's `user_email`, D-037) |

**Non-secret env** (plain Cloud Run vars, set at the 9.5d deploy — listed here so nothing is forgotten):
`VJA_AUTH_REQUIRED=1`, `VJA_COOKIE_SECURE=1`, `VJA_PUBLIC_BASE_URL=https://role-feed.com`,
`VJA_FRONTEND_DIST=/app/frontend/dist` (already the image default, D-060). `VJA_CORS_ORIGINS` stays unset
(SPA is same-origin in prod).

Layer-2 routes default in code to `anthropic/claude-haiku-4-5` (extraction) and
`anthropic/claude-sonnet-4-6` (matching), so D-090 Block 1 adds no Cloud Run env or secret. A later cutover must
mount its provider key in both complete `ship.sh` secret lists and set `VJA_EXTRACT_MODEL` and/or
`VJA_MATCH_MODEL` as preserved non-secret env; do not switch a route before its eval block is approved.

> Cloud Run's runtime service account needs `roles/secretmanager.secretAccessor` to read these — granted
> at the 9.5d deploy when the service account is known.

## 6. Google OAuth (console)

1. https://console.cloud.google.com → **APIs & Services → OAuth consent screen**: User type **External**,
   publishing status **Testing**. Add Hayden + any demo users as **Test users** (Testing mode skips
   Google's app-verification review — fine for the demo audience).
2. **Credentials → Create credentials → OAuth client ID → Web application**.
   - Authorized redirect URI: `https://role-feed.com/auth/callback`
   - (Add the `https://<service>-<hash>-uc.a.run.app/auth/callback` fallback once the Cloud Run URL exists
     at 9.5d.)
3. Copy the client ID + secret → Secret Manager (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, §5).

The redirect URI must be `https://` (the app builds it from `VJA_PUBLIC_BASE_URL`, D-059) — matches the
domain, not the proxy's internal `http`.

## 7. Resend sending domain (console + Cloudflare DNS)

Verification is **async** — do this early so it's green by 9.5d.

1. https://resend.com → **Domains → Add Domain** → `role-feed.com`.
2. Resend shows SPF + DKIM (+ optionally DMARC) records. Add them in **Cloudflare DNS** (DNS-only, not
   proxied — these are mail records, leave the cloud grey).
3. Wait for Resend to show the domain **Verified**. Then `VJA_DIGEST_FROM=digest@role-feed.com` (§5) can
   send to any recipient (replaces the `onboarding@resend.dev` sandbox that only mailed your own account).

## 8. Artifact Registry

```sh
gcloud artifacts repositories create "$AR_REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Rolefeed container images"
```

The 9.5d image push target: `${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/rolefeed:<tag>`.

---

## Hand-off to 9.5d (cutover) — done when all green

- [ ] GCP project `role-feed-prod` exists, billing linked, four APIs enabled
- [ ] Neon DB created (AWS us-east-2), `+psycopg` URL reach-tested
- [ ] All 8 secrets present (`gcloud secrets list`)
- [ ] OAuth web client created with the `https://role-feed.com/auth/callback` redirect URI
- [ ] Resend domain `role-feed.com` Verified (SPF/DKIM in Cloudflare)
- [ ] Artifact Registry repo `rolefeed` exists (`gcloud artifacts repositories list`)

**9.5d (next block, not here):** `docker build` + push → Cloud Run service (API+SPA) + Cloud Run Job
(`vja-nightly`) + Cloud Scheduler trigger; map the custom domain; `alembic upgrade head` on Neon;
suppressed baseline run; load Hayden's profile; flip `VJA_AUTH_REQUIRED=1` + `VJA_COOKIE_SECURE=1`;
`/security-review`. Full sketch in `docs/12-cloud-deploy-plan.md` §9.5d.

---

## Redeploying (`ship.sh`) — Phase A / D-066

Once 9.5c+9.5d are done and the `rolefeed` service + `vja-nightly` Job exist, **routine code
redeploys are one command**:

```sh
./deploy/gcp/ship.sh          # build → push → deploy service → update Job → smoke
./deploy/gcp/ship.sh --force  # skip the dirty-working-tree confirmation
```

It captures the `CUTOVER.md` flags so no deploy forgets `--platform linux/amd64`, a secret mount, or
the Job image update: builds+pushes the image tagged with the current short SHA, re-asserts the full
proven service/Job config (secrets, SA, `--allow-unauthenticated`), then smokes `/api/health` and an
anonymous `/api/postings?vertical=…` → **401** to prove the auth guard survived. Locked values
(`PROJECT_ID`/`REGION`/`AR_REPO`/`RUNTIME_SA`) are env-overridable defaults; **no secret values live in
the script** (Secret Manager by name only).

**Guards are preserved, never set** — the script passes no `--set-env-vars`, so `VJA_AUTH_REQUIRED` /
`VJA_COOKIE_SECURE` / `VJA_PUBLIC_BASE_URL` (CUTOVER §9) carry across untouched; it can't reopen auth.
On a clean deploy it prints the one-command **rollback** naming the prior revision:

```sh
gcloud run services update-traffic rolefeed --region us-central1 --to-revisions=<PREV>=100
```

**Scope:** redeploy of already-provisioned resources only. It does **not** migrate the schema
(`alembic upgrade head` stays a deliberate manual step — CUTOVER §3), seed, or change the domain /
OAuth redirect URIs. First-time stand-up is still `CUTOVER.md`.

---

## CI/CD (9.6 / D-068) — merge-triggered auto-deploy

Once WIF is set up (below), **merging to `main` deploys prod automatically**: the `deploy` job in
`.github/workflows/ci.yml` runs after every CI gate is green (`needs: [gates, postgres, frontend,
secrets]`), authenticates to GCP keylessly via Workload Identity Federation, and execs this same
`ship.sh` (with `ROLLBACK_ON_SMOKE_FAIL=1`, so a failed smoke auto-rolls traffic back to the prior
revision). One code path — the proven secret/SA/guard config lives only here, never copied into YAML.

**Triggers:** push to `main` (post-merge) **or** a manual **Run workflow** from the Actions tab
(`workflow_dispatch`) — never on PRs. `ship.sh --force` still runs manually as the break-glass path.

### One-time GCP setup (Hayden — needs `gcloud`/console; not runnable in-sandbox)

Keyless: GitHub's OIDC token is federated to a dedicated deploy service account. No key is ever
downloaded or stored. Paste the §"Locked values" block into your shell first, then:

```sh
export REPO="haydenham/vertical-job-agent-starter"   # owner/repo, adjust if renamed
export POOL="github-pool"
export PROVIDER="github-provider"
export DEPLOYER="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

gcloud services enable iamcredentials.googleapis.com sts.googleapis.com

# 1. WIF pool + an OIDC provider restricted to THIS repo (the attribute-condition is the security boundary)
gcloud iam workload-identity-pools create "$POOL" --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --location=global --workload-identity-pool="$POOL" \
  --display-name="GitHub OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository == '${REPO}'"

# 2. Dedicated deploy SA + least-privilege roles (deploy Run, actAs the runtime SA, push images)
gcloud iam service-accounts create github-deployer --display-name="GitHub Actions deployer"
for role in roles/run.admin roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$DEPLOYER" --role="$role"
done
# actAs the RUNTIME SA (the one ship.sh sets on the service/job) — required or `run deploy` is denied:
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="serviceAccount:$DEPLOYER" --role=roles/iam.serviceAccountUser
# (RUNTIME_SA = 850723734041-compute@developer.gserviceaccount.com, ship.sh default)

# 3. Let the GitHub repo's OIDC identity impersonate the deploy SA
POOL_ID="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${REPO}"

# 4. Print the two values to put in GitHub repo VARIABLES (Settings → Secrets and variables → Actions → Variables):
echo "GCP_WIF_PROVIDER=${POOL_ID}/providers/${PROVIDER}"
echo "GCP_DEPLOY_SA=${DEPLOYER}"
```

These two are **repo variables, not secrets** — they're resource identifiers, and WIF means there's no
credential to hide. The Secret Manager mounts are unchanged; `ship.sh` still references them by name.

### First run + ordering rule

- **First run:** Actions tab → the **CI** workflow → **Run workflow** (`workflow_dispatch`). Watch `deploy`
  build, roll the service + `vja-nightly`, and smoke green (`/api/health` ok + anon 401). Then a real merge
  to `main` proves the push path.
- **Schema-changing PRs — migrate first.** CD deploys **code only**; migrations stay manual (D-025/D-068).
  Alembic does **not** load `.env`; a bare command targets the default local SQLite DB. Use the
  explicit production sequence **before merging** (D-083):

  ```bash
  export VJA_DATABASE_URL="$(gcloud secrets versions access latest \
    --secret VJA_DATABASE_URL --project role-feed-prod)"
  uv run alembic current
  uv run alembic upgrade head
  uv run alembic current
  unset VJA_DATABASE_URL
  ```

  The production image's startup guard refuses readiness when Neon is at a known older revision,
  leaving the prior Cloud Run revision serving; it does not replace the manual migration. (A
  one-click `workflow_dispatch` migration workflow remains a possible future convenience.)
- **Rollback:** the deploy auto-rolls back on a failed smoke; for a bad revision that *passed* smoke, the
  rollback command is printed in the job log (`gcloud run services update-traffic rolefeed …`), or run
  `ship.sh` locally.

This is **9.6**; the thin `ship.sh` (D-066) it wraps stays the manual break-glass. First-time resource
stand-up is still `CUTOVER.md`.
