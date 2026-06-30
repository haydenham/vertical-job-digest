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
for s in ANTHROPIC_API_KEY RESEND_API_KEY VJA_DATABASE_URL VJA_SESSION_SECRET \
         GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET VJA_DIGEST_FROM VJA_DIGEST_RECIPIENT; do
  gcloud secrets create "$s" --replication-policy=automatic
done

# add a version (example — reads value from stdin, nothing hits the shell history file):
printf '%s' "$VALUE" | gcloud secrets versions add VJA_DATABASE_URL --data-file=-
```

Values to load:

| Secret | Source |
|---|---|
| `ANTHROPIC_API_KEY` | existing (Layer-2 extraction + matching) |
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
