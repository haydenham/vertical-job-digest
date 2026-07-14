# Cutover & go-live runbook (Phase 9.5d — deploy, migrate, flip, verify)

Deploys the 9.5b image **into** the resources 9.5c provisioned, then goes live. This is the **9.5d** block:
one-time, hand-driven ops. The provisioning prereqs live in `deploy/gcp/README.md` (9.5c); its "Hand-off to
9.5d" checklist must be all-green before you start here.

Plan of record: `docs/12-cloud-deploy-plan.md`. Ledger: `docs/11` §3.

> **No secret values in this file or the repo.** Secrets live in **Secret Manager** and are referenced by
> name; Cloud Run mounts them at deploy. The only place real values land is Secret Manager (prod) and a
> git-ignored local `.env` (for the local migrate/seed steps).

**Ordering principle — safe not sorry:** `artifact → schema → seed → deploy(auth OFF) → smoke → domain →
auth ON`. Nothing user-facing goes live until after the `*.run.app` smoke test; the auth guards flip **last**
so you're never debugging a broken deploy and a 401 at the same time.

## Locked values (from 9.5c / D-061)

| Var | Value |
|---|---|
| `PROJECT_ID` | `role-feed-prod` (#850723734041) |
| `REGION` | `us-central1` |
| `AR_REPO` | `rolefeed` (Artifact Registry Docker repo) |
| `DOMAIN` | `role-feed.com` (Cloudflare Registrar + DNS) |
| Service name | `rolefeed` (Cloud Run service) |
| Job name | `vja-nightly` (Cloud Run Job) |
| Neon | AWS us-east-2, pooled `postgresql+psycopg://…` (in `VJA_DATABASE_URL`) |

```sh
export PROJECT_ID=role-feed-prod
export REGION=us-central1
export AR_REPO=rolefeed
export DOMAIN=role-feed.com
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/rolefeed:$(git rev-parse --short HEAD)"
gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"
```

---

## 1. Build + push the image

```sh
gcloud auth configure-docker "${REGION}-docker.pkg.dev"      # one-time: docker → Artifact Registry auth
docker build --platform linux/amd64 -t "$IMAGE" .            # ⚠ see gotcha
docker push "$IMAGE"
```

> **⚠ `--platform linux/amd64` is mandatory.** This laptop is Apple Silicon (arm64); `docker build` defaults
> to arm64, and Cloud Run runs amd64 — an arm64 image deploys but **crashes on start** with an exec-format
> error. Always pass the platform flag (or `docker buildx`).

## 2. Grant the runtime service account secret access

Cloud Run's default runtime SA is `${PROJECT_NUMBER}-compute@developer.gserviceaccount.com`
(`PROJECT_NUMBER` = `850723734041`). It needs to **read** the secrets, or the service fails to start:

```sh
export RUNTIME_SA="850723734041-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor"
```

(Project-level grant is fine here — the project holds only Rolefeed's secrets. Per-secret bindings are the
tighter alternative if you ever co-tenant.)

## 3. Migrate the Neon schema (run locally against Neon)

Neon is a cloud DB; "locally" means the **`alembic` process runs in your shell** and connects out to Neon —
exactly what your reach-test did. No Cloud Run Job needed (last session assumed the laptop couldn't reach
5432; it can).

```sh
export VJA_DATABASE_URL=$(gcloud secrets versions access latest --secret VJA_DATABASE_URL --project "$PROJECT_ID")
uv run alembic upgrade head
uv run alembic current                 # sanity: prints the head revision now applied to Neon
```

## 4. Baseline seed (local, Layer-1 only — no LLM, no email)

Same `VJA_DATABASE_URL` in your shell. This stamps `first_seen_at` across the universe so the **first real
nightly digest is a normal delta, not a monster** (D-061 decision). `vja-run` is fetch→diff→persist only —
Layer 1, so **no Anthropic spend and no send**.

```sh
uv run vja-import-employers data/seed/employers_seed.csv   # seed CSV → employers rows in Neon (path is required)
uv run vja-run                         # fetch → diff → persist (stamps first_seen_at); no extract/match/send
uv run vja-load-profiles               # your matching profile → profiles row (or use the /upload UI post-launch)
```

> `postings.in_scope` is stamped at the first **nightly extract**, not by `vja-run`, so the dashboard's
> in-scope set fills in after the first scheduled run. Expected — the baseline is only about `first_seen_at`.

## 5. Deploy the Cloud Run service — **auth OFF**, for smoke

Deploy with secrets mounted but **without** the auth/redirect flips, so you can smoke the raw service on its
`*.run.app` URL first.

```sh
gcloud run deploy rolefeed \
  --image "$IMAGE" \
  --region "$REGION" \
  --allow-unauthenticated \
  --service-account "$RUNTIME_SA" \
  --set-secrets "ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,RESEND_API_KEY=RESEND_API_KEY:latest,VJA_DATABASE_URL=VJA_DATABASE_URL:latest,VJA_SESSION_SECRET=VJA_SESSION_SECRET:latest,GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID:latest,GOOGLE_CLIENT_SECRET=GOOGLE_CLIENT_SECRET:latest,VJA_DIGEST_FROM=VJA_DIGEST_FROM:latest,VJA_DIGEST_RECIPIENT=VJA_DIGEST_RECIPIENT:latest"
```

- `--allow-unauthenticated` is **Cloud Run's** IAM (lets the public reach the container) — orthogonal to the
  app's own `VJA_AUTH_REQUIRED` login gate. Keep it on; the app enforces its own auth.
- `VJA_FRONTEND_DIST=/app/frontend/dist` is already the image default (D-060) — no need to set it.
- The service needs `ANTHROPIC_API_KEY` (upload→backfill matching) + DB + session + OAuth; `RESEND`/`DIGEST_*`
  are mounted too so nothing is missing if a code path touches them. Cost guards default safely
  (`VJA_BACKFILL_MAX_POSTINGS`=100, `VJA_DAILY_LLM_BUDGET_USD`=$5) — set explicitly only to override.
- Optional: `--min-instances=1` avoids cold starts + keeps a warm Neon connection; default 0 is cheapest.

Grab the service URL: `gcloud run services describe rolefeed --format='value(status.url)'`.

## 6. Staged smoke on the `*.run.app` URL (before domain + before auth)

Add `https://<the-run.app-host>/auth/callback` as a **second** OAuth redirect URI (console → the 9.5c web
client) so login works on this temporary host. Then, with `URL` = the run.app URL:

```sh
curl -s "$URL/api/health"                      # {"status":"ok"}
curl -s "$URL/" | head -c 200                  # Rolefeed SPA (index.html)
curl -si "$URL/upload" | head -1               # 200 (SPA deep-link catch-all, D-059)
curl -s "$URL/api/postings" | head -c 200      # JSON (auth still off → anonymous default profile)
```

Then in a browser: log in with Google end-to-end on the run.app host. **Do not proceed until login
round-trips.** (This staged smoke is the safety net the bare §9.5d sketch lacked.)

## 7. Map the custom domain

```sh
gcloud run domain-mappings create --service rolefeed --domain "$DOMAIN"
gcloud run domain-mappings describe --domain "$DOMAIN" --format='value(status.resourceRecords)'
```

Add the returned record(s) in **Cloudflare DNS** (DNS-only / grey cloud — Cloud Run terminates its own TLS).
Wait for the managed cert to go green (`gcloud run domain-mappings describe … --format='value(status.conditions)'`),
then confirm `https://role-feed.com/api/health` serves.

## 8. Deploy the nightly Cloud Run Job + Cloud Scheduler trigger

Same image, entrypoint overridden to `vja-nightly` (the D-031 trigger swap — no second build):

```sh
gcloud run jobs create vja-nightly \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --command /app/.venv/bin/vja-nightly \
  --task-timeout 21600 \
  --max-retries 0 \
  --set-secrets "ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,RESEND_API_KEY=RESEND_API_KEY:latest,VJA_DATABASE_URL=VJA_DATABASE_URL:latest,VJA_DIGEST_FROM=VJA_DIGEST_FROM:latest,VJA_DIGEST_RECIPIENT=VJA_DIGEST_RECIPIENT:latest"

# Cloud Scheduler → Jobs Admin :run API (nightly; matches the launchd 06:00 local trigger)
gcloud scheduler jobs create http vja-nightly-trigger \
  --location "$REGION" \
  --schedule "0 6 * * *" --time-zone "America/Chicago" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/vja-nightly:run" \
  --http-method POST \
  --oauth-service-account-email "$RUNTIME_SA"
```

Prove it before trusting the cron: `gcloud run jobs execute vja-nightly --region "$REGION"` and watch logs
(`gcloud run jobs executions list --job vja-nightly`). The Job needs DB + Anthropic (extract/match) + Resend +
`VJA_DIGEST_*` (send) — but **not** OAuth/session (it has no HTTP surface).

**Task-attempt policy (D-086):** keep the timeout at **21,600 seconds (6h)** and automatic task retries at
**zero**. The nightly processes verticals sequentially and sends each vertical immediately after its Layer-2
pass; it is not yet delivery-idempotent across Cloud Run attempts. On 2026-07-14 the old 7,200-second task sent
aviation, timed out during grid, then `maxRetries=1` restarted the whole command and sent aviation a second
time. Six hours gives the current beta workload headroom; a process-level failure is an operator-reviewed
manual rerun until per-execution delivery idempotency is built. `ship.sh` reasserts both values on every deploy.

## 8b. Weekly discovery agent (Phase 10.2 — NOT yet enabled)

The Layer-3 discovery agent (`vja-discover`) has the same trigger shape as the nightly (D-031: one image,
entrypoint override + a Cloud Scheduler trigger), but it's **ready-but-off** — do NOT create these until its
live per-run cost is measured (D-071). Run it manually first (`vja-discover --vertical grid_power_software
--limit 5 --dry-run` prints the metered `est_cost`), then decide the weekly cadence. When you do enable it:

```sh
# Discovery Job: same image, entrypoint → vja-discover. Needs DB + OpenAI ONLY (no Resend/digest).
gcloud run jobs create vja-discover \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --command /app/.venv/bin/vja-discover \
  --args "--vertical,grid_power_software" \
  --set-secrets "OPENAI_API_KEY=OPENAI_API_KEY:latest,VJA_DATABASE_URL=VJA_DATABASE_URL:latest"

# Weekly Cloud Scheduler → Jobs Admin :run API (mirrors the launchd Mon-07:00 template)
gcloud scheduler jobs create http vja-discover-trigger \
  --location "$REGION" \
  --schedule "0 7 * * 1" --time-zone "America/Chicago" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/vja-discover:run" \
  --http-method POST \
  --oauth-service-account-email "$RUNTIME_SA"
```

One Job/trigger per vertical (distinct `--args` + trigger name), or a wrapper. Proposals land as `proposed`
rows; promote them with `vja-review` — they stay inert until approved (only `active` employers are fetched).

## 9. Flip the prod guards — **last**

```sh
gcloud run services update rolefeed --region "$REGION" \
  --update-env-vars VJA_AUTH_REQUIRED=1,VJA_COOKIE_SECURE=1,VJA_PUBLIC_BASE_URL=https://role-feed.com
```

Set the OAuth client's redirect URI to the final `https://role-feed.com/auth/callback` (keep or drop the
run.app fallback). Then confirm:

```sh
# NB: /api/postings requires a `vertical` param — without it FastAPI returns 422 (param validation runs
# before auth), NOT 401. Pass a real vertical to actually exercise the auth guard:
curl -si "https://role-feed.com/api/postings?vertical=grid_power_software" | head -1   # 401 (anon refused, D-055)
```

…and a full browser login round-trips on `role-feed.com` (cookie is `Secure`; redirect is the https domain).

> **⚠ Networks that block newly-registered domains (D-067).** If `role-feed.com` **resets the TLS connection**
> (RST right after ClientHello) while the mapping reads `Ready`/`CertificateProvisioned` and DNS is correct,
> suspect a **corporate/DNS filter blocking newly-registered domains**, *not* Cloud Run. Confirm from a
> different network (phone hotspot); it typically ages out ~30 days post-registration, or ask IT to allowlist.

## 10. Verify email end-to-end

Resend domain `role-feed.com` should already show **Verified** (9.5c §7). Send a real test digest to an
external address to prove SPF/DKIM deliver from `digest@role-feed.com` (not just the `resend.dev` sandbox):
trigger one `vja-nightly` execution (step 8) with a loaded profile, or a targeted `vja-digest` run. Confirm it
lands in an inbox, not spam.

## 11. Rollback (keep handy)

Cloud Run keeps every revision. If a deploy is bad:

```sh
gcloud run revisions list --service rolefeed --region "$REGION"
gcloud run services update-traffic rolefeed --region "$REGION" --to-revisions=<PREVIOUS_REVISION>=100
```

Instant, no rebuild. (Written down so it isn't improvised under pressure.)

## 12. Security review + docs

- Run **`/security-review`** on the full cutover diff (the docs/11 §3.1 gate) before announcing.
- Update: `docs/11` §3 checkboxes; `DECISIONS.md` (the cutover ADR); `docs/INVARIANTS.md` (auth-required now
  **ON** in prod; prod surfaces live); `CLAUDE.md` Phase 9 → 9.5 ✅; WORKLOG.

---

## Done when green (hand-off out of 9.5)

- [x] Image built `--platform linux/amd64` + pushed to Artifact Registry
- [x] Runtime SA has `secretmanager.secretAccessor`
- [x] `alembic upgrade head` applied to Neon (`alembic current` = head)
- [x] Baseline seed run (employers imported, `first_seen_at` stamped, profile loaded — 9,773 postings / 2 profiles)
- [x] Service deployed; `*.run.app` smoke green incl. a login round-trip
- [x] Custom domain mapped, cert green, `https://role-feed.com` serves (off corporate wifi — see D-067 note)
- [x] `vja-nightly` Job + Scheduler created; a manual `jobs execute` succeeded (D-063 fixed Layer-2)
- [x] Guards flipped: anon `/api/postings?vertical=…` → 401 (browser login round-trip: verify off-office-wifi)
- [ ] Real test digest delivered to an external inbox from `digest@role-feed.com`
- [ ] `/security-review` clean; docs updated (INVARIANTS/DECISIONS/docs-11/CLAUDE) — docs done in `docs/13` session

> **Product not yet beta-ready.** The cloud cutover is done, but the **onboarding/dashboard flow is broken**
> for a fresh account (one-vertical-per-user routing — D-064/065). Fix before inviting users:
> **`docs/13-onboarding-and-shipping-plan.md`** (Phase A ship-script → Phase B overhaul).

**Deferred past go-live (note, don't silently forget):** deletion/data-subject endpoint (docs/11 §3.1),
per-IP/edge rate-limiting + captcha (§3.3 — OAuth bounds abuse meanwhile), spend-trend observability/alerting
(§3.5), Neon PITR retention confirm. And the **post-launch deploy loop** — see `docs/11` §4.
