# Work Log

Append-only record of working sessions — a narrative backup to git history.
Newest entry on top. One entry per working session. Keep it terse: what changed, why, what's next.

---

## 2026-07-06 — Phase A · thin scripted deploy `ship.sh` (D-066 → done)

**First of the two pre-beta blocks (`docs/13`): the thin redeploy script, so shipping Phase B — the onboarding
overhaul — is one command, not a hand-walk of `CUTOVER.md`.** Branch `feat/phase-a-ship-script` (off `main`
@ `0e5beb1`). Code-only + docs; no cloud ops run in-session.

**Did:** `deploy/gcp/ship.sh` (new, executable) — build (`--platform linux/amd64`, the mandatory arm64→amd64
footgun) → push (tag = short SHA) → capture prior serving revision → `gcloud run deploy rolefeed` (re-asserts the
full CUTOVER §5 config: 8 secrets, runtime SA, `--allow-unauthenticated`) → `gcloud run jobs update vja-nightly`
(same image, D-031 trigger-swap; 5 secrets, no OAuth/session) → smoke (`/api/health` = ok **and** anon
`/api/postings?vertical=grid_power_software` → **401**) → print the `update-traffic` rollback naming the prior
revision. **Key contract:** the script passes **no** `--set-env-vars`, so the prod guards (`VJA_AUTH_REQUIRED`/
`VJA_COOKIE_SECURE`/`VJA_PUBLIC_BASE_URL`, CUTOVER §9) are preserved untouched — it can't reopen auth; the 401
smoke is the tripwire if that ever regresses. No secret **values** in the script (Secret Manager by name);
locked values are env-overridable defaults. Redeploy-only — schema (`alembic`), seed, domain, OAuth URIs stay
manual (CUTOVER). Dirty-tree → confirm/`--force` (tag is the SHA). `deploy/gcp/README.md` gains a "Redeploying
(`ship.sh`)" section.

**Design calls (approved in plan):** re-assert full config each deploy (self-healing vs drift; cost = the
`--set-secrets` replace-semantics, kept identical to CUTOVER + loudly commented) over image-only; guards
preserved-never-set; rollback = capture-prior + print (no auto-rollback).

**Decisions:** **D-066 → done.** No new INVARIANT (a redeploy script isn't a cross-cutting rule; CUTOVER +
README cover it). `docs/13` Phase A ticked.

**Verified:** `bash -n` clean; `chmod +x`. `shellcheck` not installed locally. **Cannot run the script here** —
no gcloud/docker/creds in-sandbox, and it's an outward-facing prod deploy. DoD's "no-op rebuild deploys
end-to-end" is Hayden-run.

**Next:** Hayden commits/PRs `feat/phase-a-ship-script` + runs a no-op `./deploy/gcp/ship.sh` to close Phase-A
DoD. Then **Phase B — onboarding/auth-UX overhaul** (the actual beta blocker): `/api/me`-driven per-user vertical
routing, real route guards (static landing → `/onboarding` → their dashboard), one-vertical write enforcement,
`prompt="select_account"`, matched-view client poll. Plus scope's **closeout** (email E2E + `/security-review`)
and the B-4 data cleanup (deactivate one of Hayden's two seed profiles).

---

## 2026-07-06 — Phase 9 · 9.5d go-live finished + found the onboarding flow is broken; planned the fix (D-064–067)

**Session picked up mid-cutover, live with Hayden. Net: the cloud cutover is done and the app is live on
`role-feed.com` with auth on — but a fresh-account walkthrough exposed that the onboarding/dashboard flow is
broken, so we specced the fix instead of inviting beta users.** Branch `docs/onboarding-and-shipping-plan`
(docs only; no code/ops in-session beyond read-only diagnostics + the two Hayden-run ops noted below).

**Go-live closeout (D-067):** Hayden flipped the prod guards (`VJA_AUTH_REQUIRED=1`, `VJA_COOKIE_SECURE=1`,
`VJA_PUBLIC_BASE_URL=https://role-feed.com`); confirmed anon `/api/postings` → **401**. The scary
**`role-feed.com` TLS reset** (RST right after ClientHello, from two networks) was **not** Cloud Run — the
mapping read `Ready`/`CertificateProvisioned`, DNS correct — it was **office wifi blocking a newly-registered
domain**; **works over hotspot.** (A delete+recreate of the mapping was a red herring; harmless.) Remaining
closeout: real email E2E + `/security-review`.

**The real finding — onboarding is broken (D-064/065):** a fresh Google account showed every step wrong:
logged-out `/` renders a **401 as an error string** (no login landing); after login the dashboard **404s**
because `active_verticals()` returns a **global, cross-user** vertical list and `Dashboard.tsx` defaults to the
sorted-first (`aviation_software`) regardless of user; the vertical picked at upload is ignored; no onboarding
gate. **Root cause:** the SPA treats vertical as a global picker, contradicting the standing (but never
documented) policy **one vertical per user** — a documentation/communication lapse, now fixed in the docs.

**Decisions:** **D-064** one-vertical-per-user made explicit (fixed at signup, immutable, no cross-user picker).
**D-065** onboarding overhaul target flow: static landing (+login CTA) → Google auth → **one page: pick vertical
+ upload résumé** → their dashboard (cleaned immediate; matched = loading via a bounded client-side poll, no new
backend; timeout → "full results after tonight's run"); adds `/api/me`, route guards, one-vertical enforcement,
`prompt="select_account"`. **D-066** ship a **thin scripted deploy** (`ship.sh`) before the fix, not full CI/CD
(deferred "9.6"). **D-067** go-live done + the corporate-wifi lesson. INVARIANTS updated: one-vertical rule
added, auth-required now **ON in prod**, the deployed global-picker flagged as a known defect.

**New doc:** `docs/13-onboarding-and-shipping-plan.md` — the plan of record for the next two blocks (**A** thin
ship-script → **B** onboarding overhaul), the beta-onboarding checklist, and the later roadmap (9.6 CI/CD,
Phase 10 discovery agent + review queue, beta hardening = expand the employer universe).

**Next (post-reset):** plan/build **Phase A** (ship-script), then **Phase B** (onboarding overhaul — the beta
blocker). Also pending: deactivate one of Hayden's two seed profiles (the dual-vertical anomaly under one email,
D-064 §B-4), finish go-live closeout (email E2E + security review), and merge this docs branch.

---

## 2026-07-02 — Phase 9 · 9.5d go-live (in progress): cloud cutover + container config-path bug fix (D-063)

**Executed most of `deploy/gcp/CUTOVER.md` live with Hayden; hit + fixed a real cutover-blocking bug.** Branch
`fix/vertical-config-path-in-container` (off `main` @ `8dcbc0a`).

**Cutover progress (ops, Hayden-driven):** image built `--platform linux/amd64` + pushed (§1); runtime-SA
secret grant (§2); `alembic upgrade head` on Neon (§3); baseline seed (§4) — 90 employers imported, `vja-run`
seeded **9,773 postings** (`first_seen_at` stamped), 2 profiles loaded (aviation + grid, both active). Service
deployed auth-OFF (§5) + `*.run.app` smoke green incl. **Google login round-trip** (§6). Custom domain
**mapped + cert green** (§7, `role-feed.com`, 8 apex A/AAAA in Cloudflare DNS-only). Nightly **Job + Scheduler
created** (§8, `0 6 * * *` America/Chicago). **Not yet done:** guard flip (§9), email E2E (§10), sec-review +
docs (§12), and merge of this branch.

**The bug (D-063):** first `vja-nightly` executions completed ok but did **zero Layer-2** — `extracted=0
matched=0 digests=none $0`, reproducibly. Root cause proven by running the deployed image: the nightly's
`for vertical in available_verticals()` got **`[]`** because `_CONFIG_DIR = Path(__file__).parents[2]/config/
verticals` assumes the repo/src layout, but the image installs vja **`--no-editable`** (site-packages), so
`parents[2]` missed and the config YAMLs (copied to `/app/config/verticals`) were never found. Local runs
(src layout) always worked → never caught pre-cloud. **Fix:** honor a **`VJA_VERTICALS_DIR`** env override
(mirrors the existing `VJA_FRONTEND_DIST` pattern, D-060 — same `--no-editable` path problem); Dockerfile sets
it to `/app/config/verticals`. Proven in-container: default → `[]`; `/app/config/verticals` → both verticals.
After rebuild+redeploy (image `b2a74fa`, + `--task-timeout=7200`/`--max-retries=1` on the Job), execution
`vja-nightly-295wd` **confirmed calling `api.anthropic.com` in the extraction phase** — Layer-2 now runs.

**Tests:** +1 regression (`test_config_dir_honors_env_override`, reloads the module under a patched env).
**Verified:** ruff + mypy clean; **372 pytest** green (was 371). Also folded two `CUTOVER.md` doc fixes
(explicit `import-employers` CSV path; the `--task-timeout` note).

**Next:** let `295wd` finish (extract ~2k → match → digest); confirm matches + first digest land; **then**
resume `CUTOVER.md` §9 guard flip → §10 email E2E → §12 sec-review/docs. **Merge `fix/vertical-config-path-
in-container` → `main`** so the deployed `b2a74fa` matches the default branch. Hayden also doing domain
follow-up.

---

## 2026-06-30 — Phase 9 · 9.5d-prep: engine hardening + cutover runbook + change-mgmt (D-062)

**Repo-side prep for the last block (9.5d go-live), no cloud ops run.** 9.5c is done+merged (PR #47 @
`74644e1`) — this session reconciles that, ships the one real pre-ship code fix, writes the executable cutover
runbook, and documents the post-launch change loop. Branch `feat/9.5d-prep`.

**Correction to last session:** D-061/WORKLOG said the laptop can't reach Neon (port-5432 filtered) so
migration had to go via a Cloud Run Job exec. Hayden reach-tested the pooled URL this session →
`neon ok`. So `alembic upgrade head` + baseline seed run **locally from his shell** — simpler, fewer moving
parts. Folded into the runbook + D-062.

**Did:**
- **Engine hardening (code)** `src/vja/db/engine.py`: `get_engine` now sets **`pool_pre_ping=True`** (all
  dialects) + **`pool_recycle=1800`** (`POOL_RECYCLE_SECONDS`, non-SQLite only) so Neon's serverless
  autosuspend can't hand out a dead pooled connection. SQLite FK-pragma listener untouched.
- **`deploy/gcp/CUTOVER.md`** (new) — the 9.5d runbook, analogue of the 9.5c `README.md`. Safety order
  `artifact→schema→seed→deploy(auth OFF)→smoke→domain→auth ON`; exact `gcloud`/`docker` commands (no secret
  values); the **`--platform linux/amd64`** gotcha (arm64 laptop → amd64 Cloud Run), runtime-SA
  `secretAccessor` grant, local `alembic`/seed, a **staged `*.run.app` smoke incl. login** before domain/auth,
  Cloud Run Job + Scheduler (`0 6 * * *` America/Chicago, matching launchd), the auth flip **last**, and a
  `update-traffic` rollback note. "Done when green" checklist.
- **`docs/11` §5 Post-launch change management** (new) — **Path A** (data → DB, no redeploy: employers via
  `vja-import-employers`, profiles via upload/`vja-load-profiles`) vs **Path B** (config/code baked in image →
  rebuild+deploy: `config/verticals/*.yaml`, scope/prefilter, fetchers, discovery agent). Maps Hayden's
  roadmap (2 new verticals + expansion + company-finder) onto the two loops; recommends a merge-triggered
  auto-deploy as a post-launch "9.6", flags moving config out of the image if churn ever hurts. Cross-linked
  from `docs/09` + the CLAUDE.md doc-map line.

**Decisions:** **D-062**. INVARIANTS: DB-access line gains the pre-ping/recycle rule. docs/12: 9.5c status →
merged via PR #47; §9.5d rewritten as an index → `deploy/gcp/CUTOVER.md`.

**Tests:** `tests/integration/test_engine.py` (+2: sqlite pre-pings/no-recycle; postgres pre-pings+recycles —
offline, `create_engine` is lazy). Rest of the suite unchanged.

**Verified:** full Python gate green — ruff format/check, mypy (110 files), import-linter (1 kept/0 broken),
`uv lock --check`, **371 pytest** (+2) on SQLite. (CI re-runs the suite on the `postgres:16` service on push;
the new engine tests are offline — `create_engine` is lazy — so they cover both dialects locally.)

**Next:** **STOP for Hayden to commit + PR** (`feat/9.5d-prep`). Then **9.5d — execute `deploy/gcp/CUTOVER.md`**
(Hayden-driven, his gcloud/console auth): build+push → deploy service (auth off) → smoke → domain → Job +
Scheduler → flip guards → test send → `/security-review` → docs. Post-launch: the §5 "9.6" auto-deploy loop.

**Branch:** `feat/9.5d-prep` (off `main` @ `74644e1`).

---

## 2026-06-30 — Phase 9 · Block 9.5c: cloud provisioning standup (D-061)

**Third 9.5 block — ops standup, no app code.** Stood up the cloud resources the 9.5d cutover deploys
*into*, live with Hayden in his consoles + a written runbook. Plan of record: `docs/12`.

**Did:**
- **`deploy/gcp/README.md`** (new) — the provisioning runbook (the cloud analogue of `deploy/launchd/`):
  variables block + locked-values table, `gcloud`-driven where reproducible, console steps marked
  (Neon/OAuth/Resend/Cloudflare), **no secret values in the repo** (→ Secret Manager), a "hand-off to 9.5d"
  green-checklist.
- **Provisioned (verified via `gcloud` reads):** GCP project **`role-feed-prod`** (#850723734041) + billing;
  4 APIs (run/artifactregistry/cloudscheduler/secretmanager, no Cloud SQL); Artifact Registry Docker repo
  **`rolefeed`** (`us-central1`); **8 secrets** loaded w/ enabled versions; **OAuth** web client in
  `role-feed-prod` (consent External/Testing, redirect `https://role-feed.com/auth/callback`); **Resend**
  domain `role-feed.com` verified + `digest@role-feed.com`; **Neon** DB (AWS us-east-2), `VJA_DATABASE_URL`
  stored **pooled + `postgresql+psycopg://`**.
- **`.env.example`** — corrected the one wrong literal (`rolefeed.com` → `https://role-feed.com` in the
  `VJA_PUBLIC_BASE_URL` example).

**Gotchas (captured in D-061 + runbook):** domain is **`role-feed.com` (hyphenated)**, not the `<rolefeed>.com`
the docs/12 table had assumed — literal differs everywhere. Neon hands out bare `postgresql://`; the
**`+psycopg` rewrite is mandatory** (re-lost it once when swapping to the pooled host — fixed, now v4). OAuth
client was first made under the wrong project, **re-created in `role-feed-prod`** (secrets @ v2). **Laptop
can't connect to Neon (local network blocks port 5432)** — irrelevant to prod (Cloud Run reaches Neon over
the cloud backbone); authoritative connect + `alembic upgrade head` runs at 9.5d via a Cloud Run Job exec.

**Decisions:** **D-061** (provisioning values locked). INVARIANTS: no change (no live cross-cutting rule
moved — the auth-required/cookie/redirect flips are still 9.5d). docs/11 §3.4 (verified sending domain) +
§3.5 (secrets store) ticked. docs/12: status line **fixed** (9.5b was stale — merged via PR #46 @ `0abbb5b`,
not "awaiting commit+PR"), 9.5c row → ✅, §9.5c rewritten as-built with the real literals.

**Tests:** none — docs/ops only, no code touched (Python/frontend gates unaffected).

**Next:** **STOP for Hayden to commit + PR** (9.5c, branch `feat/cloud-deploy-9.5c`). Then **9.5d — cutover/
go-live:** build+push image → Cloud Run service (API+SPA) + Cloud Run Job (`vja-nightly`) + Cloud Scheduler;
map custom domain; `alembic upgrade head` on Neon; suppressed baseline run; load Hayden's profile; flip
`VJA_AUTH_REQUIRED=1` + `VJA_COOKIE_SECURE=1` + `VJA_PUBLIC_BASE_URL`; add the `*.run.app` OAuth fallback URI;
real test send; `/security-review`. Full sketch in `docs/12` §9.5d.

**Branch:** `feat/cloud-deploy-9.5c` (off `main` @ `0abbb5b`).

---

## 2026-06-29 — Phase 9 · Block 9.5b: containerization (D-060)

**Second 9.5 block — packages the app as one image so 9.5c/d are pure ops.** Code+infra, no GCP needed.
One multi-stage image, **two run targets** (D-031): `vja-api` (Cloud Run service, default CMD) + `vja-nightly`
(Cloud Run Job, entrypoint override) — no second build. Plan of record: `docs/12`.

**Did:**
- **`Dockerfile`** (repo root): stage `web` = `node:24-bookworm-slim` (**Debian/glibc, not alpine** — dodges
  the musl `@rollup/rollup-linux-x64-musl` build break; matches local node v24.7) `npm ci && npm run build`;
  runtime = `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`, **non-editable** `uv sync` in two cache layers
  (deps → project), copies `frontend/dist` in, `CMD vja-api --host 0.0.0.0` (honors `$PORT`). Bakes runtime
  data the wheel doesn't carry: `config/`, `migrations/`+`alembic.ini`, `data/seed/`. **No secrets/DB URL in
  the image** — all runtime env.
- **`VJA_FRONTEND_DIST`** (`app.frontend_dist_dir()` helper, replaces the `_FRONTEND_DIST` module const): the
  non-editable install moves the package off the repo layout `parents[3]/frontend/dist` assumed, so the dist
  dir is now explicit config (image sets `/app/frontend/dist`; dev/CI default to repo layout). This is what
  *unlocks* the clean (non-editable, immutable-artifact) install — editable-in-prod is the anti-pattern it
  avoids. The 9.5a serving tests now drive via the env, not the removed const.
- **`.dockerignore`**: `.venv`, `node_modules`, host `frontend/dist` (rebuilt in-image), `data/*.db`, `.git`,
  caches, `tests`/`docs`/`deploy`, local `.env`.

**Decisions:** **D-060**. INVARIANTS: SPA-serving line rewritten (`frontend_dist_dir`/`VJA_FRONTEND_DIST` +
one-image/two-entrypoints). docs/12: 9.5b → ✅ + smoke command + **fixed the stale 9.5a "awaiting commit+PR
on `feat/cloud-deploy`" header** (9.5a is merged to `main` via PR #45 @ `fd347cd`). docs/11 §3.5 gains the
containerization checkbox.

**Tests:** `tests/unit/test_api_helpers.py` (+2: `frontend_dist_dir` env-override / repo-layout default);
`tests/integration/test_serving.py` (3 funcs repointed from the removed const to `VJA_FRONTEND_DIST`).

**Verified:** full Python gate green — ruff format/check, mypy (110 files), import-linter (1/0), `uv lock
--check`, **369 pytest** (+2) on SQLite (no schema change). `docker build` clean; **local prod-parity smoke**:
`/api/health`→ok, `/` + `/upload` (catch-all) → Rolefeed SPA, `/assets/*`→200, unknown `/api`→404, binds
`0.0.0.0:8000`, both entrypoints present (601 MB image).

**Next:** **STOP for Hayden to commit + PR** (9.5b, branch `feat/containerization`). Then **9.5c — provision**
(GCP project + **Neon** PG + a `.com` via Cloudflare + Secret Manager + Artifact Registry + OAuth creds) —
ops/docs, needs the GCP project + domain. Then 9.5d cutover/go-live. See `docs/12`.

**Branch:** `feat/containerization` (off `main` @ `1775f87`, post-9.5a-PR-#45 merge).

---

## 2026-06-29 — Phase 9 · Block 9.5a: deploy-readiness app hardening (D-059)

**First 9.5 block — code-only, no infra.** Closes the app-level seams a TLS-terminating proxy (Cloud Run) +
an enforced auth gate expose, so 9.5b–d are pure packaging + ops. Surfaced by this session's loose-ends
audit; every prod behavior is **env-gated** so local dev defaults are unchanged. Plan of record:
`docs/12-cloud-deploy-plan.md`.

**Did (all `src/vja/api/`):**
- **Cookie hardening** (`auth.py`: `cookie_https_only`/`session_max_age`, `_env_truthy` factored out of
  `auth_required`): `SessionMiddleware` now gets `https_only` (`VJA_COOKIE_SECURE`, off in dev),
  `same_site="lax"` (Strict breaks Google's OAuth redirect), `max_age` (`VJA_SESSION_MAX_AGE`, 14d default).
- **HTTPS OAuth redirect_uri** (`auth.oauth_redirect_uri`): prefers `VJA_PUBLIC_BASE_URL` → `https://…/auth/
  callback` (else `url_for`), fixing the Cloud-Run `redirect_uri_mismatch`; `api_main`'s `uvicorn.run` gains
  `proxy_headers=True, forwarded_allow_ips="*"` as the fallback-path backstop.
- **SPA deep-link catch-all** (`app.py: _mount_spa`): replaced `StaticFiles(html=True)` with explicit
  `/assets` + a trailing `/{full_path:path}` → `index.html` for client routes (hard-refresh of `/upload`
  no longer 404s), real files served verbatim, unknown `/api`·`/auth` still 404. Mount gated on a real
  `index.html` (found a stale empty `frontend/dist` locally that the old `is_dir()` guard would have mounted).
- **Container bind** (`app.py: _parse_args`): `--host`/`--port` default from `VJA_API_HOST`/`PORT` (Cloud Run
  injects `$PORT`; container binds `0.0.0.0`); dev stays 127.0.0.1:8000; flags override. `load_dotenv` moved
  before parse so `.env` feeds defaults. **CORS** doc-noted only (already env-driven, same-origin in prod).
- **`.env.example`** gains the four knobs (`VJA_COOKIE_SECURE`, `VJA_SESSION_MAX_AGE`, `VJA_PUBLIC_BASE_URL`,
  `VJA_API_HOST`), all dev-safe defaults.

**Decisions:** **D-059**. INVARIANTS: SPA line (catch-all built) + login line (cookie/redirect built,
env-gated) rewritten. docs/11 §3.2 parenthetical updated. docs/12 9.5a → ✅.

**Tests:** `tests/unit/test_api_helpers.py` (+8 — cookie flag default/on, max_age default/override, redirect-uri
prefers base / falls back, parse-args env + flag override) · `tests/integration/test_serving.py` (+3 funcs —
index/assets/deeplink served; `/api`·`/auth` not masked; no mount without a real build).

**Verified:** full Python gate green — ruff format/check, mypy (110 files), import-linter (1/0), `uv lock --check`,
**367 pytest** (+12) on SQLite (no schema change → Postgres path unaffected; CI re-runs it). Frontend untouched.

**Next:** **STOP for Hayden to commit + PR** (9.5a). Then **9.5b — containerization** (multi-stage Dockerfile
building the SPA + serving under FastAPI; one image, `vja-api` + `vja-nightly` entrypoints) — also code-now, no
GCP needed. 9.5c/d (provision + cutover) wait on the GCP project + the `.com`. See `docs/12` for each block's spec.

**Branch:** `feat/cloud-deploy` (off `main` @ `250aa38`).

---

## 2026-06-29 — Doc close-out: Phase-8 Part B cash-in confirmed run (record correction)

**Not new code — fixing doc drift.** Hayden flagged that the Phase-8 Part B cash-in run *did* execute, yet
every recent entry's "Next" still listed it as "still-open (orthogonal, no code)." Confirmed against
`data/vja.db` — the run happened:
- **pipeline_runs:** #12 (2026-06-25) **2705 new** / 324 closed and #16 (2026-06-26) **2312 new** / 579
  closed — vs normal nightly deltas of ~11–78 new.
- **Extraction (Haiku):** 444 (06-25) + 655 (06-26) [+ an earlier 875 on 06-23]; nightly is ~4–24/day.
- **Matching (Sonnet):** 35 (06-25) + 184 (06-26) [+ 152 on 06-23]; nightly ~1–9/day. 425 matches total.
- **Digests:** `sent` daily through 2026-06-29 (nightly live via launchd).

The run already left a code fingerprint — **D-056** (digest closure rollup) fixed the ~922-closure wall it
exposed (pipeline_run #16's 579 closed + the 2-day backlog). What was missing was a close-out; the stale
"still-open: Part B cash-in" boilerplate got copy-pasted forward through the 9.1→9.4 "Next" sections (which,
being append-only history, are left as-written — this entry supersedes them).

**Corrected record:** Phase-8 Part B cash-in = **DONE**. Of that orthogonal pair, **only the Phenom fetcher
remains open.** No INVARIANTS/DECISIONS change (D-056 already captured the only decision the run produced).

**Worth an eye (not action):** `postings.in_scope` = 384 / 11 457; **zero `backfill`-trigger matches** (all
425 are `nightly`) — both expected (the dashboard floors on `in_scope`; no signup→backfill has run yet).

**Next:** 9.5 — cloud deploy + Postgres cutover + verified email domain + security review (+ the deferred
flips: `VJA_AUTH_REQUIRED` on, prod OAuth redirect URIs, cookie hardening, SPA deep-link catch-all). Then
Phenom (the last open Phase-8 item). This doc fix rides on the 9.5 branch.

**9.5 planned (this session) → `docs/12-cloud-deploy-plan.md`** (plan of record; survives chat resets). Four
sub-blocks: **9.5a app hardening** (cookies/proxy-HTTPS-redirect/SPA-catch-all/bind — code, testable now) ·
**9.5b containerization** (multi-stage Dockerfile — code) · **9.5c provision** (GCP project + **Neon** PG +
a `.com` via Cloudflare + Secret Manager) · **9.5d cutover/go-live** (deploy, `alembic upgrade`, suppressed
baseline run, Resend domain verify, flip auth/cookie guards, `/security-review`). Locked: **Neon not Cloud
SQL** (URL-swap ethos, ~$0), Cloud Run, buy a `.com`, **fresh DB + baseline run** (no sqlite→PG migration).
9.5a/b are code-now (no GCP needed); 9.5c/d are ops-later. **Resume by reading docs/12 → next ☐ block.**

**Branch:** `feat/cloud-deploy` (off `main` @ `250aa38`, post-9.4-PR-#44 merge).

---

## 2026-06-29 — Phase 9 · Block 9.4: multi-user frontend (Rolefeed) (D-058)

**The UI that makes 9.2 auth + 9.3 upload reachable.** Frontend-only — **no backend code touched**; every
endpoint already existed (`/auth/*`, `/api/me`, `POST /api/profiles`) and CORS already allowed credentials.
A user can now sign in with Google, upload a résumé, and see *their* matches. Product renamed **Rolefeed**
(user-facing brand; codebase/CLI stay `vja`). Four forks, all the recommended option:
1. **Routed pages** (`react-router-dom`) over conditional rendering. 2. **`VJA_AUTH_REQUIRED` stays off in
9.4** (dashboard anonymous-readable; login only gates `/upload`) — flips at 9.5. 3. **Optimistic upload
feedback** (no status endpoint, honours D-057). 4. **Credentialed fetches** so the session resolves the
user's own profile (the 9.2 seam).

**Did (all in `frontend/`):**
- **Branding → Rolefeed:** wordmark (`$ rolefeed▮`), `index.html` `<title>`, `package.json` name/description.
- **Routing:** added `react-router-dom`; `main.tsx` wraps `<BrowserRouter><AuthProvider>`; `App.tsx` is now
  the shell (brand + auth-aware nav) + `<Routes>`. Old App body extracted verbatim → `pages/Dashboard.tsx`
  (behaviour unchanged; its data-flow tests moved to `Dashboard.test.tsx`).
- **Auth client:** `api.ts` gains `credentials: "include"` on every call + `loginUrl`/`fetchMe`/`logout`/
  `uploadResume` (+ typed `ApiError` carrying status + server `detail`, `User`/`ProfileCreated` types).
  `auth/useAuth.ts` (context+hook, no component → clean Fast-Refresh) + `auth/AuthProvider.tsx` (probes
  `/api/me` once; 401 ⇒ anonymous, a valid state).
- **Pages:** `Login.tsx` (Google sign-in anchor → `loginUrl()`), `Upload.tsx` (soft-gated → `/login`;
  vertical select + file input → `uploadResume` → optimistic "résumé received (v{n})" + dashboard link;
  413/422/429 surface inline). New CSS in `theme.css` (nav, panel, btn, form, subbar).

**Decisions:** **D-058**. INVARIANTS: D-042 SPA line rewritten (Rolefeed, routes, credentialed fetches,
deep-link caveat) + new résumé-upload-surface line; auth-gate line now "stays off through 9.4". CLAUDE.md
Phase 9 list 9.4 ✅. docs/11 §3.2 gains the frontend-UI checkbox + auth-gate note.

**Tests:** frontend gate green — eslint (0 warnings), `tsc -b --noEmit`, **vitest 34 passed** (8 files; +
`api` upload/login/me, `AuthProvider`, `Login`, `Upload`, `App` shell/nav; `Dashboard` carries the old App
tests). `npm run build` bundles clean (tsc + vite). No Python touched → backend suite unaffected.

**Known follow-up (9.5, noted in D-058/docs):** prod `StaticFiles(html=True)` 404s a hard-refresh of
`/upload`|`/login` (client-side nav is fine) — needs a catch-all → `index.html` at deploy, alongside the
`VJA_AUTH_REQUIRED` flip + prod OAuth redirect URIs + cookie hardening.

**Next:** **STOP for Hayden to commit + PR** (9.4). Then **9.5 — cloud deploy + Postgres cutover + verified
email domain + security review** (+ the deferred flips above). Still-open orthogonal (no code): Phase-8
Part B cash-in run + the Phenom fetcher. Optional dev check: a real Google round-trip locally (set
`GOOGLE_CLIENT_*` + `VJA_SESSION_SECRET`, run FastAPI :8000 + `VITE_API_BASE=…:8000 npm run dev`).

**Branch:** `feat/multi-user-frontend` (off `main` @ `d5864db`, post-9.3-PR-#43 merge). *(Prior WORKLOG entry
was stale — its "STOP to commit+PR 9.3" already happened as PR #43.)*

---

## 2026-06-27 — Phase 9 · Block 9.3: résumé upload + signup→backfill + cost guards (D-057)

**The product's first write path.** A logged-in user uploads a résumé → a profile is created → the D-039
signup backfill matches it against the last 5 days of open postings. Backend-only (upload UI is 9.4; prod
hardening is 9.5). Four forks, all run through Hayden taking the recommended option:
1. **Formats = text/markdown + text PDF** (`pypdf`), scanned/OCR deferred. 2. **Background backfill** (202 +
`profile_id`, `run_backfill` as a threadpool `BackgroundTask`) over inline-sync / defer-to-nightly.
3. **Cost guards = per-backfill cap + global daily ceiling**, skip cooldown, defer captcha/edge to 9.5.
4. **`POST /api/profiles` (multipart), no status endpoint** (no schema change).

**Did:**
- **`src/vja/resume.py`** (new leaf, D-033 adapter): `extract_resume_text(filename, data)` — UTF-8
  text/markdown + text-PDF (`pypdf`, routed by `%PDF-` magic or `.pdf`); scanned/empty/non-text/oversize/
  too-long all raise `ResumeError`. **Never logs the text/bytes** (PII, docs/11 §3.1). New deps `pypdf` +
  `python-multipart` (FastAPI form parsing).
- **Cost guards** (`match.py` + `db/matches.py`): `_match_profile` gains `max_postings`; `run_backfill`
  passes `VJA_BACKFILL_MAX_POSTINGS` (default 100) — **nightly stays uncapped** (`None`). `count_matches_since`
  + `estimate_daily_spend` (count since midnight × `_NOMINAL_MATCH_USD` ~$0.01, no per-match ledger) +
  `check_backfill_budget` raising `BackfillBudgetExceeded` over `VJA_DAILY_LLM_BUDGET_USD` (default $5).
- **profiles repo:** `upsert_profile` gains `user_id` (stamped on insert + reactivate; CLI path unchanged →
  NULL→linked-by-email per D-055); new `get_profile(engine, id)`.
- **`POST /api/profiles`** (`api/app.py`, behind `require_user`): budget→file-read(413)→adapter(422)→
  vertical config(404)→`upsert_profile(user_id=…)`→`get_profile`→`BackgroundTasks(run_backfill)`→**202**
  `{profile_id, vertical, resume_version}`. `run_backfill` referenced as a module global (monkeypatchable).
  `.env.example` gains the two guard knobs.

**Decisions:** **D-057**. INVARIANTS: Cost & safety gains the guard line; Auth & identity gains the
first-write-endpoint line; the backfill line now notes the posting cap. docs/11 §3.3 backfill-guard box
ticked + rate-limit/captcha deferral noted; §3.1 PII-logging note. CLAUDE.md Phase 9 block list (9.1–9.3 ✅).

**Tests:** `tests/unit/test_resume.py` (+11 — text/md/PDF extraction via a hand-built correct-xref PDF;
scanned/unreadable/non-UTF8/empty/whitespace/oversize/too-long rejections). `test_backfill.py` (+4 — cap
slices to N; `estimate_daily_spend` arithmetic; budget raises over / passes under). `test_api.py` (+6 —
upload 401-unauth / 202 creates+links `user_id`+triggers backfill / 422 bad file / 404 unknown vertical /
429 over budget / 413 oversize; `run_backfill` stubbed so the BackgroundTask never hits Anthropic).

**Verified:** full Python gate green — ruff format/check, mypy (108 files), lint-imports (1 kept/0 broken),
`uv lock --check` in sync, **355 pytest** (+21) on SQLite (Postgres via `VJA_TEST_DATABASE_URL` when set —
no new schema, so the dialect path is unaffected). No migration this block (no schema change).

**Next:** **STOP for Hayden to commit + PR** (9.3). Then **9.4 — multi-user frontend** (login UI + résumé
upload form over this endpoint + signup→backfill UX). Still-open (orthogonal, no code): the Phase-8 Part B
cash-in run + the Phenom fetcher. Optional outward-facing follow-up: send the held digest (re-check baseline
first).

**Branch:** `feat/resume-upload-backfill` (off `main` @ `8d03159`, post-9.2-PR-#41 / D-056-PR-#42 merge).

---

## 2026-06-26 — Pre-9.3: summarize digest closures by company (D-056)

**Did:** Render-only fix to the digest-quality bug the Phase-8 cash-in run exposed — the body listed every
closed role as one bullet, so a 2-day backlog (~940 closures: Boeing 241, GE Vernova 147, Airbus 134…) would
render as a wall burying the ~66 new roles (kill-criterion violation; the nightly would re-send it unattended).
`src/vja/digest/render.py`: **≤10 closures enumerate as before; >10 roll up by company** —
`N roles across C companies:` + top-10 (`• Company — n`, count desc via `Counter.most_common`) +
`…and M more companies (P roles)` tail, with `_plural` for company/role singular-plural. Symmetric in text +
HTML (new `_closed_html`, `_rollup_split` shared). **Subject keeps the true count; `contents_to_dict` keeps the
full closed list** — only the human-facing body summarizes (audit/D-037 completeness intact). New/quarantine
paths untouched; no DB/schema/dep change.

**Decisions:** **D-056** (dual-mode, threshold 10, company rollup; body-only). INVARIANTS digest section gains
the closure-rollup line.

**Tests:** `tests/unit/test_digest_render.py` +5 — many-closures rollup (subject true count, per-company counts,
no per-role enumeration), tail collapse + singular wording (11 single-role companies), the 10/11 boundary
(incl. "1 company" singular), few-closures-stay-detailed, audit-keeps-all-15-when-summarized. Failing-first
repro per D-021.

**Verified:** eyeballed the real 922-closure backlog shape → 11 lines, new role on top, subject "922 closed".
Full Python gate green — ruff format/check, ruff, mypy (106 files), lint-imports (1/0), `uv lock --check` (no
new deps), **334 pytest** (+5). Render-only → Postgres path unaffected (no SQL touched).

**Next:** **STOP for Hayden to commit + PR.** Then **9.3 — résumé upload + signup→backfill + cost/abuse guards**
(behind `require_user`, D-055). **Optional follow-up (outward-facing, confirm first):** send the held digest —
re-check current baseline/state, since nightly/data may have moved since the cash-in.

**Branch:** `fix/digest-closure-summary` (off `main` @ `bf76767`, post-9.2-PR-#41 merge).

---

## 2026-06-26 — Phase 9 · Block 9.2: auth foundation — Google OAuth + `users` + read-API authz (D-055)

**Built the layer 9.3 depends on** (its résumé-upload / signup→backfill write endpoints sit behind login).
Three forks run through Hayden, all taking the recommended option:
1. **Real Google OAuth, exercised locally** (not stubbed-till-deploy) — so 9.3's writes are genuinely
   gateable now. 2. **`users` table + nullable `profiles.user_id` FK** (not email-as-sole-key) — clean
   multi-user shape, migration trivial + born-on-both-dialects (D-054). 3. **Authz layer + deferred hard
   enforcement** (not auth-required-now) — local dashboard stays usable before the 9.4 login UI; existing
   API tests stay green.

**Did:**
- **Schema/migration** (`db/schema.py` + `7d5b69c46786`): `users` (`google_sub` uniq/nullable, `email`
  uniq/not-null, `name`, `created_at`) + nullable `profiles.user_id` FK. `op.batch_alter_table` so the FK
  lands on SQLite (table rebuild) and Postgres alike. Hand-fixed the autogen to render `UTCDateTime` as
  `sa.DateTime(timezone=True)` (repo convention) and name the FK; `alembic check` → no drift.
- **`db/users.py`:** `upsert_user_by_google` (idempotent on `sub` → adopt email-only row → insert) +
  `_link_profiles` (backfills `profiles.user_id` by email = the D-027→FK bridge, so the seed profile
  attaches on first login) + `get_user`. `profiles.user_email` kept → match/digest/nightly untouched.
- **`api/auth.py`:** Authlib Google OIDC registry (inert/503 until `GOOGLE_CLIENT_*`; lazy discovery),
  `get_current_user`/`require_user` deps, `auth_required()` reading `VJA_AUTH_REQUIRED`, `session_secret()`.
- **`api/app.py`:** `SessionMiddleware`; `/auth/login` + `/auth/callback` (exchange → upsert+link → session
  → redirect) + `/auth/logout` + `/api/me`; `_resolve_profile(…, user)` — authed resolves own profile (403
  on another's `profile_id`), unauthenticated keeps the single-active default, `VJA_AUTH_REQUIRED` ⇒ 401.
- **Deps/config:** `authlib` + `itsdangerous` (`uv lock`); mypy override for un-stubbed authlib; `.env.example`
  gains `GOOGLE_CLIENT_ID/SECRET`, `VJA_SESSION_SECRET`, `VJA_AUTH_REQUIRED` + the localhost redirect note.
- **Migration bug found in the live login (D-021):** the first real OAuth login 500'd on `no such table: users`
  — the prod `vja.db` hadn't been upgraded. Upgrading then crashed: the `profiles.user_id` **batch rebuild**
  (SQLite can't add a FK in place) drops+recreates `profiles`, and with `PRAGMA foreign_keys=ON` (the app's
  runtime setting, which `migrations/env.py` was inheriting via `get_engine`) the DROP tripped `matches → profiles`
  on the **populated** DB. The empty-table fixture never hit it. **Fix:** `env.py` now runs migrations on a
  dedicated engine with **SQLite FKs OFF** (set at connect — the pragma is a no-op in a txn; the app keeps FKs
  ON) — exactly SQLite's documented ALTER procedure. Regression test `test_add_user_id_on_populated_db` seeds a
  `matches`→`profiles` row, upgrades, asserts success + data preserved. Real `vja.db` then migrated cleanly
  (backed up first; 3 profiles / 394 matches / 11 327 postings intact) after clearing the partial-migration
  orphans (`users` + `_alembic_tmp_profiles`) the aborted first attempt left behind (alembic uses
  non-transactional DDL on SQLite, so the failed run isn't atomic).

**Decisions:** **D-055**. INVARIANTS gains an **Auth & identity** section; docs/11 §3.2 (users+authz) ticked,
§2 seam status updated.

**Tests:** new `tests/integration/test_auth.py` (users-repo idempotency/email-adoption/profile-link;
login 503-unconfigured + redirect-to-Google; callback creates+links+sessions with the token exchange
mocked; `/api/me` 401/200; logout). Extended `test_api.py` with authz (own-profile resolution, 403 on
another's id, `VJA_AUTH_REQUIRED` 401). The live Google handshake is a **manual** check, not in the suite.

**Verified:** full Python gate green — ruff format/check, mypy (106 files), lint-imports (1 kept/0 broken),
`uv lock --check` in sync, **329 pytest on SQLite and 329 on Postgres** (local PG 15 throwaway on :5433,
Docker still unavailable; CI uses 16) — the `users`+FK migration proven on both dialects (D-054), incl. the
new populated-DB regression. **Live login verified end-to-end:** `/auth/login` 302s to Google with the real
client (live OIDC discovery), the callback authenticated + created the user after the migration fix.

**Next:** **STOP for Hayden to commit + PR** (9.2). Hayden provisions the Google OAuth client (consent
screen + Web credentials, redirect `http://localhost:8000/auth/callback`) to run the manual login check.
Then **9.3 — résumé upload + signup→backfill + cost/abuse guards** (behind `require_user`). Still-open
(orthogonal, no code): the Phase-8 Part B cash-in run + the Phenom fetcher.

**Branch:** `feat/auth-foundation` (off `main` @ `30ac867`, post-9.1-PR-#40 merge).

---

## 2026-06-26 — Phase 9 plan + Block 9.1: Postgres path CI-verified on both dialects (D-054)

**Planned Phase 9** (cloud + multi-user product, D-047) into 5 PR-sized blocks and built the first.
Reasoning with Hayden reframed his "frontend-first" instinct: two of the three "frontend" items are
full-stack and order-coupled — résumé **upload** is the first *write* endpoint (API is read-only by
invariant, D-005/D-041) and spends LLM tokens via signup→backfill (§3.3), so it sits **behind login**;
the vertical **toggle** is dropped as a user feature (1-vertical-per-user limiter → a real user only sees
their own vertical). Accepted leans: **Google OAuth** (zero passwords), **GCP** (Cloud Run + Cloud Run Job
via Cloud Scheduler — the D-031 trigger swap — + Cloud SQL + Secret Manager), **1-vertical/user** default.
Block order of record: **9.1 Postgres-CI spine** ✅ · 9.2 auth (OAuth + `users` + authz) · 9.3 résumé
upload + signup→backfill + cost/abuse guards (gated by auth) · 9.4 multi-user frontend · 9.5 cloud deploy +
full Postgres cutover + verified email domain + security review.

**Did (9.1):** turned D-025's "just a URL swap + `alembic upgrade`" from faith into a CI gate, so every later
block's security/PII tables are born-on-Postgres-verified. **Zero behavior change.**
- `psycopg[binary]>=3.2` → `[project.dependencies]` (SQLAlchemy-native `postgresql+psycopg://`); SQLite stays
  the default. `uv lock` (3 new pkgs: psycopg, psycopg-binary, tzdata).
- `tests/conftest.py`: the single `migrated_engine` fixture honors `VJA_TEST_DATABASE_URL` — unset → today's
  `tmp_path` SQLite (unchanged); set → that Postgres with a per-test `DROP SCHEMA public CASCADE; CREATE
  SCHEMA public` before `alembic upgrade head` (clean isolation on one shared service DB, no dependence on
  migration `downgrade()`s).
- `.github/workflows/ci.yml`: new `postgres` job (service `postgres:16`) re-runs the offline suite with the
  env var set. pytest-only (lint/types/imports/lock/frontend are dialect-agnostic — covered by `gates`).

**Decisions:** **D-054** (Postgres path CI-verified on both dialects; psycopg; per-test schema reset; no
dialect gaps found). INVARIANTS DB line updated; docs/11 §1 DB row + §3.5 first item ticked.

**Dialect gaps:** **none.** The 315-test suite (schema built via `alembic upgrade head` per test → migrations
exercised) passed on Postgres first run. The Core portability choices held: `native_enum=False` VARCHAR+CHECK
enums, `UTCDateTime` over `DateTime(timezone=True)` (→ `timestamptz`), `sa.JSON`, integer `server_default`s.

**Verified:** **315 pytest on Postgres** (local PG 15, throwaway instance — Docker unavailable, so a Homebrew
`postgresql@15` datadir on :5433; CI uses 16) **and 315 on SQLite**; full Python gate green — ruff
format/check, mypy (103 files), lint-imports (1 kept/0 broken), `uv lock --check` in sync.

**Next:** **STOP for Hayden to commit + PR** (9.1). Then **9.2 — auth foundation** (Google OAuth + `users`
table + read-API authz, plugging the docs/11 §2 `(vertical, profile_id)` seam). Still-open from the prior
session (orthogonal, no code): the Phase-8 **Part B cash-in run** (`vja-import-employers` → `vja-run` →
extract → match) and the **Phenom** fetcher — neither blocks Phase 9.

**Branch:** `feat/postgres-ci-portability` (off `main` @ `7516e91`, post-D-053-PR-#39 merge).

---

## 2026-06-25 — Re-opened-posting fix (D-053) — unblocking the Phase-8 cash-in run

**Did:** Session task was "reason on next steps." Reasoned that Phase 8 had shipped 5 fetchers (39→44
coverage) with **zero paid pipeline runs** since the aviation vertical — coverage was theoretical. Chose
to **cash in the coverage** with a real extract→match run before building more (Phenom). The free
count-gate (`vja-run`) surfaced **two blockers** before any spend:
- **Stale DB (free fix):** `vja-import-employers` was never re-run after the Phase-8 seed edits → the 8
  verified P8 tenants (Constellation/Exelon/SIG/ICE/SITA/NextEra/Southern/Vitol) sat as stale
  `detected`/`layer2` rows with no endpoint ("cannot build endpoint"); 7 correctly-parked tenants were
  stale-`active` and wrongly attempted. Seed is correct + importer is a `(vertical,name)` upsert → one
  re-import fixes all 15. **Deferred to the operational Part B** (after this PR merges).
- **Re-opened-posting bug (this PR):** 10 employers (Vistra, S&P Global, Jane Street, AES, Xcel, Fluence,
  Shell Trading, Yes Energy, Wood Mac, Kraken) crashed with `UNIQUE constraint failed:
  postings.employer_id, postings.external_id` — a posting that closed (D-009, never deleted) then
  reappeared landed in `diff.new`, and `insert_posting` collided with the surviving closed row, aborting
  the employer's whole transaction (new + closures discarded).

**Fix:** `sync_employer` now intersects `diff.new` with a new `closed_index` and routes a reappeared id to
a new `reopen_posting` (UPDATE in place) instead of `insert_posting`. Reopen **resets `first_seen_at`** so
the role surfaces as new again (Hayden's call over "reopen silently"); clears `extracted_at` only when the
body's `content_hash` moved (cache-aware, D-035); same non-NULL `source_updated_at` guard as `bump`.
`diff.py` stays pure set arithmetic. A `reopened` counter rides `SyncResult`/`RunSummary` + the
`vja-run`/nightly summary lines (observability only — `pipeline_runs.postings_new` keeps counting true
inserts; no schema change).

**Decisions:** **D-053** (reopen-in-place + surface-as-new + cache-aware re-extract + reopened
observability-only). INVARIANTS diff/data-model section gains the reopen line (next to D-009).

**Tests:** `tests/integration/test_pipeline.py` +3 — reopen resurrects the same row (no IntegrityError,
`first_seen_at` advanced, counted `reopened` not `new`); changed-body reopen clears `extracted_at`;
identical-body reopen preserves the cached extraction. The production `vja-run` crash is the
failing-in-prod repro (D-021). 14 pass in the file.

**Verified:** full Python gate green — ruff format/check, mypy (42 files), lint-imports (1 kept/0 broken),
**315 pytest** (+3), `uv lock --check` in sync (no new deps).

**Next:** **STOP for Hayden to commit + PR.** Then **Part B (operational, no code):** `vja-import-employers`
→ `vja-run` (now clean) → count-gate + authorize → `vja-extract` (Haiku) → `vja-match` (Sonnet) → look at
the digest/dashboard. The BP Trading single Workday job missing `externalPath` is an isolated, non-blocking
upstream data quirk to note, not fix. Then Phenom (the deferred Phase-8 build order) once the cash-in
proves the current coverage's worth.

**Branch:** `fix/reopen-closed-postings` (off `main` @ `78693c0`, post-Radancy-PR-#38 merge).

---

## 2026-06-24 — Phase 8 · Block 4: Radancy/TalentBrew Tier-C fetcher + platform-probe resequence (D-052)

**Did:** With Tier-B done, the docs' next item was the generic Layer-2 **LLM-read** tail. A Step-0
reconnaissance pass changed the plan.

- **Research → decision (both run through Hayden):** live-probed the `custom`/`layer2` tail and found it's
  mostly **JS-rendered SPAs or bot-blocked** (United/Southwest = Phenom shells, NextEra = Radancy, Aurora =
  React, GridStatus = 403, Mercuria = marketing page) — served HTML carries almost no job content, so a
  literal "LLM-read-the-page" fetcher would read nothing on the employers that matter. **Decision 1:** probe
  the two big multi-tenant platforms (Phenom, Radancy) for a clean API *before* the LLM-read (the iCIMS
  lesson, D-048; faithful to D-017). **Decision 2:** Radancy first (grid priority, D-022); Phenom next.
- **Step-0 crack (Radancy):** the JS landing page is empty, but `GET {endpoint}/search-jobs/results?
  CurrentPage=&RecordsPerPage=&SearchType=5` returns the jobs **server-rendered** in a
  `<table id="searchresults">` (uniform TalentBrew markup → one generic fetcher). Always HTML
  (`Accept: json` ignored) → an **HTML-parse** fetcher (the repo's first; +`beautifulsoup4`). Total from the
  table `aria-label` ("Results 1 to 25 of 288"); rows in `tr.data-row`; the `/job/{slug}/{id}` link gives id
  + apply_url, the `jobLocation`/`jobDate` cells give location + a real date. Captured 2 fixtures (NextEra
  list + one job detail, D-019).
- **Fetcher** (`src/vja/fetchers/radancy.py`): list-only + **paginate-or-fail** on the aria-label total
  (mis-parse/short-tally → `FetchError`, never a partial → no false closures) + lazy `fetch_detail`
  (`div.jobdescription`, routed by the same `extract._DETAIL_RESOLVERS` map — now 4). `external_id` = the
  `/job/{slug}/{id}` **path** (Workday `externalPath` parity — the detail URL needs the slug; the id alone
  302s to an error page; and `fetch_detail(employer, external_id)` can't widen without coupling fetchers to
  the db layer / breaking import-linter). `updated_at` from `jobDate` parsed `%b %d, %Y` → ISO (a D-030 win
  Workday lacks). Endpoint is **explicit per-tenant** (no slug). Wired into the registry + resolver map.
- **Seed:** NextEra `layer2 → verified` (endpoint = search base; 288 open at probe). NRG/National Grid/
  L3Harris **parked `proposed`/`detected`, kept `radancy`** (NRG 200 but different results markup; National
  Grid 403; L3Harris 301) — because wiring `RADANCY` into `SUPPORTED_ATS_TYPES` means
  `active_fetchable_employers` would otherwise select an endpointless active row and fail (the D-051
  invariant; Workday P4.2 parked-tenant precedent, D-032). Coverage **43→44** (grid 32→33).

**Decisions:** **D-052** (probe-platforms-before-LLM-read resequence + Radancy via server-rendered
`/search-jobs/results` HTML; HTML-parse fetcher; list-only + paginate-or-fail + lazy detail; path-as-id;
`bs4` dep; NextEra onboarded, 3 parked; 43→44). INVARIANTS (fetcher-order line + new Radancy contract line +
the resolver-map line now 4), `docs/07` (platform table split, build-order items 7–10, endpoint encoding,
coverage math 59%→61%), CLAUDE Phase-8 line, `data/seed/README.md` both status blocks.

**Tests:** `tests/unit/test_radancy.py` (16: real-fixture golden mapping + total parse, single-page,
pagination by CurrentPage, paginate-or-fail/truncation, mid-pagination error, empty board, missing
table/total, row missing link/title, missing location+date, unparseable date, HTTP 500, `fetch_detail`
description + error-page redirect + HTTP error); `tests/live/test_radancy_live.py` (opt-in NextEra smoke +
detail-has-description); `test_extract.py` (parametrized Radancy lazy-detail dispatch); `test_registry.py`
(Radancy supported); `test_employers_import.py` counts (43→44, +Radancy; endpoint-or-slug invariant relaxed
since Radancy is endpoint-only).

**Verified:** full Python gate green — ruff format/check, mypy (103 files), lint-imports (1/0, no new layer
edge), **312 pytest** (+17), `uv lock` in sync (1 new dep: `beautifulsoup4`). Live smoke (2): NextEra returns
well-formed postings + apply_url under `/job/`; `fetch_detail` returns a real description body.

**Next:** **STOP for Hayden to commit + PR** (Block 4). Then **Phenom** (the `/widgets/` JSON API — United/
Southwest/Thales), then Tier-C singletons, then the Layer-2 LLM-read tail for the genuinely-custom remainder.
NRG/National Grid/L3Harris await a verified search base (config-only onboard). No paid extract/match run yet.

**Branch:** `feat/radancy-fetcher` (off `main` @ `bad8ede`, post-Block-3-PR-#37 merge).

---

## 2026-06-24 — Phase 8 · Block 3: SmartRecruiters + Oracle HCM Tier-B fetchers (D-050, D-051)

**Did:** Built the next two Phase-8 (Tier-B) fetchers in one combined PR (Hayden's call), completing the
documented build order's Tier-B set (iCIMS → Workable → **SmartRecruiters → Oracle**). Both are list-only
for the description, so both reuse — and generalize — Workday's lazy-detail path.

- **Step-0 feasibility probe (the gate):** live-probed both APIs. **SmartRecruiters** =
  `api.smartrecruiters.com/v1/companies/{slug}/postings` — clean JSON, `totalFound`/offset pagination,
  uniform → one generic fetcher (Vitol slug `Vitol`, 42 open). **Oracle ORC** =
  `{host}/hcmRestApi/.../recruitingCEJobRequisitions?…&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber={CX_n}`
  — clean JSON, `TotalJobsCount` pagination (Southern Co: `emje.fa.us6`, `CX_1001`, 105 open). Two probe
  findings shaped the build: (1) **both lists omit the description** (SR has none; Oracle's `External*Str`
  are empty in list mode) → both are list-only like Workday, not iCIMS-rich; (2) Oracle's `expand` param
  is **required** (without it: no `requisitionList`). Captured 4 fixtures (list + detail each, D-019).
- **SmartRecruiters fetcher** (`src/vja/fetchers/smartrecruiters.py`): list-only + paginate-or-fail on
  `totalFound` + `fetch_detail` (the `jobAd.sections` body). `apply_url` **constructed**
  (`jobs.smartrecruiters.com/{slug}/{id}`, verified 200 — no detail fetch for the link, D-008);
  `external_id = id` (D-016); `location` from `fullLocation` with empty comma-segments collapsed;
  `updated_at = releasedDate` (D-030). Slug-derivable → added to `endpoints.py` `_DERIVED_TEMPLATES`.
- **Oracle fetcher** (`src/vja/fetchers/oracle.py`): list-only + paginate-or-fail on `TotalJobsCount`
  (limit/offset appended as `finder` sub-params) + `fetch_detail` (the `ExternalDescriptionStr` body,
  host + siteNumber parsed off the seeded list endpoint). `apply_url = {careers_url}/job/{Id}` (verified);
  `external_id = Id`; `location = PrimaryLocation`; `updated_at = PostedDate`. Explicit per-tenant endpoint
  (no `endpoints.py` change). Both wired into the registry.
- **Generalized the lazy-detail dispatch** (`src/vja/extract.py`): the Workday-only `if` in `_source_text`
  is now a per-ATS `_DETAIL_RESOLVERS` map (Workday + SmartRecruiters + Oracle); the default resolver
  dispatches by `ats_type`. Adding a list-only ATS is now a one-line wire-up. Injection point stays a
  single callable (existing tests unchanged in shape).
- **Seed (config/data):** Vitol `detected → verified` (slug `Vitol`); Southern Company `detected →
  verified` (Oracle list endpoint w/ `siteNumber=CX_1001`). **Honeywell + Con Edison reclassified
  `oracle_hcm/detected → custom/layer2`** — their clean ORC host isn't exposed (Honeywell's vanity domain
  proxies the REST API 302→404; Con Edison stays on coned.com). This preserves the "supported `ats_type` ⟹
  has a working endpoint" seed invariant (`active_fetchable_employers` filters only on status + supported
  ATS, so an endpointless oracle_hcm row would otherwise be selected and fail). Notes say to flip back to
  `oracle_hcm` + add the endpoint when a host is curated. Coverage **41→43** (grid 30→32; aviation 11).

**Decisions:** **D-050** (SmartRecruiters via the public postings API; slug-derived; list-only + lazy
detail; apply_url constructed; 41→42). **D-051** (Oracle ORC via the CE REST API; explicit per-tenant
endpoint; list-only + lazy detail; Southern onboarded, Honeywell/ConEd → Layer 2 pending curation; 42→43).
INVARIANTS (fetcher-order line + SR/Oracle contract lines + the new resolver-map line), `docs/07` (table +
build-order + encoding + coverage math), CLAUDE Phase-8 line, `data/seed/README.md` both status blocks.

**Tests:** `tests/unit/test_smartrecruiters.py` (19) + `tests/unit/test_oracle.py` (19) — fixture mapping,
apply_url construction, pagination, paginate-or-fail/truncation, mid-pagination error, location handling,
`fetch_detail` mapping + siteNumber/host parse, every transport/parse/shape/missing-field → `FetchError`;
`tests/live/test_{smartrecruiters,oracle}_live.py` (opt-in Vitol/Southern smoke + detail-has-description);
`test_extract.py` (parametrized SR/Oracle lazy-detail dispatch); `test_registry.py` (both supported;
unsupported example switched to Jobvite); `test_endpoints.py` (SR slug-derivation); `test_employers_import.py`
counts (41→43, +SmartRecruiters/+Oracle; grid fetchable 30→32).

**Verified:** full Python gate green — ruff format/check, mypy (100 files), lint-imports (1/0), **295 pytest**
(+38), `uv lock` in sync (no new deps). Live smoke (4): Vitol 42 well-formed postings + detail body; Southern
Co 105 + detail body; both `updated_at` populated, apply_url resolves.

**Next:** **STOP for Hayden to commit + PR** (Block 3). Tier-B fetchers are now complete; next is the
**Layer-2 LLM-read tail** (the custom/portal remainder + HN/niche). Honeywell + Con Edison await curation
(canonical Oracle host + siteNumber → config-only onboard). No paid extract/match run yet.

**Branch:** `feat/smartrecruiters-oracle-fetchers` (off `main` @ `06b77e4`, post-Workable-PR-#36 merge).

---

## 2026-06-24 — Phase 8 · Block 2: Workable Tier-B fetcher via the embed-widget API (D-049)

**Did:** Built the second Phase-8 (Tier-B) fetcher — Workable — following the documented build order
(iCIMS → **Workable** → SmartRecruiters/Oracle → Layer-2 tail). Chose Workable over the other Tier-B
targets because it's the most de-risked (clean slug-derivable JSON, one tenant already verified).

- **Step 0 feasibility probe (the gate):** live-probed `apply.workable.com/api/v1/widget/accounts/{slug}`
  across both seed tenants. Clean, unauthenticated JSON, **uniform** → one generic fetcher (D-017/D-004).
  Two findings that shaped the contract: (1) the widget returns **all open jobs in one response** —
  `{"name","description","jobs":[…]}`, **no `total`/pagination** — so it's a single-response ATS like
  Greenhouse/Lever, *not* paginate-or-fail like iCIMS/Workday; (2) **`?details=true` is required** for the
  inline `description` HTML. Vortexa = 5 open, Energy Aspects = 0 (matches its historical probe). Captured
  `tests/fixtures/workable.json` (Vortexa, D-019).
- **Fetcher** (`src/vja/fetchers/workable.py`, `WorkableFetcher`): modeled on Greenhouse (single GET +
  map-all). False-closure guard = the **single-request contract** (clean 200 = complete set; empty `jobs`
  = legitimate 0 open; any transport/parse/shape error → `FetchError`, diff never runs on a partial). Map:
  `external_id = shortcode` (D-016), `apply_url = url` (public posting page), `location` = `city, state,
  country` joined (full names → better Stage-B US signal than the bare ISO codes in `locations[]`),
  `updated_at = published_on` (a D-030 freshness win — no detail fetch), `description` inline HTML.
- **Endpoint derivation:** added Workable to `endpoints.py` `_DERIVED_TEMPLATES` (slug-derived, per
  `docs/07`; host is uniform, unlike iCIMS's per-tenant careers domains), template includes `?details=true`.
  Wired into the registry.
- **Seed (config/data):** Vortexa `detected → verified` (slug `vortexa`, 5 open); Energy Aspects re-verified
  (API valid, 0 open). Both now fetchable → grid 28→30, total **39→41**.

**Decisions:** **D-049** (Workable via the embed-widget API; slug-derivable; single-response false-closure
guard; coverage 39→41). INVARIANTS (fetcher-order line + new Workable contract line), `docs/07` (table +
build-order + resolved Vortexa fixup), CLAUDE Phase-8 line, `data/seed/README.md` grid status block updated.

**Tests:** `tests/unit/test_workable.py` (11: fixture mapping, single-response/all-jobs, empty board,
`created_at` fallback, missing-location→None, transport/HTTP-500/non-JSON/missing-`jobs`/missing-`shortcode`/
empty-field → `FetchError`); `tests/live/test_workable_live.py` (opt-in Vortexa smoke); `test_endpoints.py`
(Workable slug-derivation); `test_registry.py` (Workable now supported); `test_employers_import.py` counts
(39→41, +2 Workable; grid fetchable 28→30).

**Verified:** full Python gate green — ruff format/check, mypy (94 files), lint-imports (1/0), **257 pytest**
(+12), `uv lock` in sync (no new deps). Live smoke: Vortexa returns 5 well-formed postings with populated
`updated_at`.

**Next:** **STOP for Hayden to commit + PR** (Block 2). Then the rest of Tier-B (SmartRecruiters — 1, clean
public API; Oracle HCM — 3, per-tenant ORC), then the Layer-2 LLM-read tail. No paid extract/match run yet.

**Branch:** `feat/workable-fetcher` (off `main` @ `ae5cb12`, post-Block-1 merge + Sabre/Amadeus).

---

## 2026-06-24 — Phase 8 · Block 1: iCIMS Tier-B fetcher via the Jibe `/api/jobs` API (D-048)

**Did:** Built the first Phase-8 (Tier-B) fetcher, kicked off by a coverage-research pass.

- **Research first (Hayden's three questions):** we fetch only **34%** of the seeded universe (grid 24/54,
  aviation 7/36); the aviation vertical looked empty (3 companies, only Boeing matching) purely for lack of
  coverage. **Garmin** — a near-perfect missed role — was seeded `custom`/`layer2` but is actually **iCIMS**.
  Decided iCIMS leads Phase 8 (highest coverage + fixes the felt gap). Shared the 38-row `layer2` tail with
  Hayden for parallel digging.
- **Step 0 feasibility probe (the gate):** the legacy `careers-{tenant}.icims.com` portal is a frame-busted
  SPA (domReplacement, no clean JSON), **but** the modern iCIMS **Career Sites (Jibe)** product exposes a clean,
  unauthenticated `GET {careers_base}/api/jobs?page&limit` → `{"jobs":[{"data":…}],"totalCount":…}`. Verified
  **uniform across tenants** (Garmin/Constellation/Exelon/SIG/ICE/SITA share every core field) → **one generic
  fetcher** works (D-017/D-004 risk retired). Captured `tests/fixtures/icims.json` (D-019).
- **Fetcher** (`src/vja/fetchers/icims.py`, `IcimsFetcher`): paginate-or-fail like Workday, but the rich list
  payload gives `apply_url` + full `description` (overview+responsibilities+qualifications joined) + real ISO
  `update_date` — **no detail fetch**, and `updated_at` populated (D-030 freshness win). `external_id = req_id`
  (D-016). Wired into the registry; endpoint is explicit per-tenant (careers domains vary), so no `endpoints.py`
  change.
- **Seed (config/data):** onboarded 6 Jibe tenants (Garmin custom→icims; Constellation/Exelon/SIG/ICE/SITA
  detected→verified, `+/api/jobs` endpoints + client_code slugs). **Alaska** (legacy portal, no Jibe API) and
  **Joby** (`/api/jobs` 404, custom site) reclassified detected→`layer2`. Fixed 2 pre-existing malformed CSV
  rows (Exelon stray trailing field; Enverus unquoted comma) — seed is now clean 14-col throughout.
- **Tail re-probe:** D-015 fingerprint over all 38 `layer2` rows found **no other Jibe tenants** (Garmin was
  the only misfile) but surfaced **Amadeus + Sabre = Workday** candidates → a later data-only PR.

**Decisions:** **D-048** (iCIMS via the Jibe career-site API; legacy/non-Jibe/auth-gated → Layer 2; coverage
31→37). INVARIANTS (fetcher-order + new iCIMS line), `docs/07`, CLAUDE Phase-8 line, `data/seed/README.md`
status blocks (also corrected the pre-existing post-D-046 RTX/Workday staleness) updated.

**Tests:** `tests/unit/test_icims.py` (11: fixture mapping, pagination, paginate-or-fail/truncation, transport/
parse/shape/missing-field errors); `tests/live/test_icims_live.py` (opt-in Garmin smoke); `test_registry.py`
(iCIMS now supported; unsupported-case switched to Oracle HCM); `test_employers_import.py` counts (31→37, +6
iCIMS; aviation 7→9).

**Verified:** full Python gate green — ruff format/check, mypy (38 files), lint-imports (1/0), **245 pytest**,
`uv lock`. Live smoke: Garmin returns **303** postings incl. "Software Engineer - Real Time Aviation Data" (US)
— the previously-invisible class of role now flows.

**Plus (same session, config-only Workday onboards from Hayden's probing):** Hayden pulled board URLs for the
dark tail. **Sabre** (`sabre:wd1:SabreJobs`, 150) and **Amadeus** (`amadeus:wd502:jobs`, 135) live-verified and
onboarded to the existing Workday fetcher (zero code) → aviation **9→11**, total **37→39** (Workday 18→20).
**Delta/Avature** investigated and left at Layer 2: `delta.avature.net` serves per-job schema.org JSON-LD but
returns a **202 bot-challenge** (empty body) server-side, so no clean list API. Counts/README/D-048 updated.

**Next:** **STOP for Hayden to commit + PR** (Block 1). Then the rest of Tier-B (Workable/SmartRecruiters/Oracle),
then the Layer-2 tail. No paid extract/match run yet — Hayden authorizes after reviewing fetch counts.

**Branch:** `feat/icims-fetcher` (off `main` @ merged PR #34).

---

## 2026-06-22 — Phase 7 · Blocks 3+4: aviation config + full end-to-end run (D-046) — architecture test PASSED

**Did:** Wrote the aviation vertical config and ran the **whole pipeline end-to-end** on it. **Headline: adding the
aviation vertical forced ZERO `src/` changes** — the D-004 architecture test passes. (Blocks 3+4 combined into one PR
per Hayden.)
- **Block 3 — config:** `config/verticals/aviation_software.yaml` (aviation `domain_vocabulary` + Stage-A `scope`
  with aviation-specific excludes [pilot, flight attendant, ramp, …] + Stage-B `prefilter` US/early-career).
  Auto-discovered by `available_verticals()`'s glob; loaded by the same `load_vertical_config`. Added
  `test_loads_real_aviation_config`.
- **Block 4 — end-to-end run** (local `data/vja.db`, gitignored; backup `data/vja.db.pre-aviation.bak`):
  - `vja-import-employers` → 36 aviation inserted, 54 grid updated, **ats-unresolved=0** (every ATS value a valid
    enum). `vja-load-profiles` → aviation profile active; **grid bumped to a new `resume_version`** (the re-tilt).
  - `vja-run --vertical aviation_software` → **3612 postings / 7 employers** (Airbus 2000, Boeing 1169, Shield AI
    391, Wisk 24, Beacon AI 17, OAG 10, FLYR 1). Stage-A in-scope **874 (24%)**.
  - `vja-extract` → **871/874** extracted (3 isolated failures), **$3.68** (Haiku). Stage-B persisted `in_scope`
    cut 874 → **110** (Airbus's mostly-EU + Boeing's senior roles correctly dropped on US/level).
  - `vja-match --vertical aviation_software` → **110/110**, **$1.71** (Sonnet). Verdicts: **1 yes · 16 maybe ·
    93 no**. The 17 relevant are **all US** entry-level/associate SWE roles (geo filter clean — no foreign leak);
    the 85% `no` rate is the willingness-to-say-no (D-007) working for a junior CS candidate vs whole-company
    aerospace boards.
  - **Grid re-match** (résumé changed → stale matches): `vja-match --vertical grid_power_software` → **41/41**,
    **$0.68**, 17 relevant. `/api/verticals` now returns **both** verticals (dashboard picker surfaces aviation).
  - **Total LLM spend: ~$6.07.**

**Finding (logged, not a defect):** the run **stress-tested the Workday fetcher** — Collins/RTX's whole-conglomerate
`cxs` board (4160) exceeds Workday's **~4000 offset cap**, so the paginate-or-fail guard (D-032) correctly refused
the truncated page rather than reading 160 roles as closures. Per the **Castleton precedent (D-032)**, RTX was
**reclassified to Layer 2 in config** (seed edit, no code) — so aviation fetchable is **7, not 8** (3 Workday). This
is the first Workday tenant big enough to hit the cap (grid's max was GE Vernova ~2376). Candidate future fetcher
improvement: offset-cap-aware Workday pagination. Probing also caught a Greenhouse **name collision** (`archer` = a
veterinary clinic, not Archer Aviation → Layer 2).

**Decisions:** **D-046** (Phase 7 aviation shipped config-only; the architecture test + the RTX finding). Also this
session, **D-047** — roadmap resequence: **P8 remaining coverage → P9 cloud migration + full product frontend
(promoted from the floating D-025 cutover, widened to auth/upload/vertical-toggle) → P10 discovery agent (demoted)**;
security posture for a free public launch folded in (cost-abuse is the dominant risk; `docs/11` is the P9 checklist).
CLAUDE.md build sequence + INVARIANTS (D-004/D-022/D-032 lines) updated.

**Tests:** `test_loads_real_aviation_config` (config loads via the same path); `test_employers_import` updated for the
RTX reclassification (aviation fetchable 8→7, Workday 4→3; combined 32→31/18). Data/config-count tests, not new src.

**Verified:** full Python gate green — ruff format/check, mypy, lint-imports (1/0), pytest, `uv lock`. **No `src/`
change in the entire phase.** Spot-checks: 17/17 aviation relevant matches US; `/api/verticals` lists both verticals.

**Next:** **STOP for Hayden to commit + PR** (Blocks 3+4). Then **Phase 8** (Tier-B fetchers + Layer-2 tail). The
aviation detected/Layer-2 tail (Delta/Avature, JetBlue/SuccessFactors, Joby/iCIMS, RTX cap, …) lights up there.

**Branch:** `feat/aviation-vertical` (off `main` @ the merged Block-2 PR).

---

## 2026-06-22 — Phase 7 · Block 2: re-tilt both resumes (config/data only)

**Did:** Re-tilted the matching résumés per vertical (the matching-profile half of the D-004 config —
still zero `src/` change).
- **Shared, real-experience edits to both résumés:** added **Optum (UnitedHealth Group) — Technology
  Development Intern** (current, top of Experience) with two bullets on **data ETL pipelines in
  Snowflake** + SQL transformations; **removed the LinkUp** role. Tech Stack updated to reflect the
  now-real tools (FastAPI, pandas, SQL/Snowflake, PostgreSQL, Redis, Google Cloud, TypeScript).
- **`hayden_aviation_resume.md`** (new): replaced the Nomi project with the **Flight Delay Cascade
  Simulator** (FastAPI + pandas / React + Vite; tail-cascade + connection-risk propagation over the U.S.
  DOT BTS dataset); Interests → Aviation & Flight Systems / Real-Time Data Systems. Sudoku Solver kept.
- **`hayden_grid_resume.md`** (edit): replaced Nomi with the **Strait of Hormuz Event Study** (FastAPI +
  React/Vite/TS; layered offline compute → read-only API; price-vs-transit event scatter); Interests →
  Energy Markets & Power Trading / Commodities & Quant.
- Bullets are **faithful to the facts Hayden gave** (project mechanics, Snowflake ETL) — no invented
  metrics. **Placeholders to confirm:** the Optum **location ("Remote") and start month ("June 2026")**.

**Decisions:** none new. Per Hayden: replace Nomi with the two projects, add Optum/Snowflake, drop LinkUp.
Note: re-tilting the grid résumé changes its text → a new `resume_version` on the next `vja-load-profiles`,
so existing grid matches go stale — Hayden chose to **re-match grid** in Block 4.

**Tests:** none added (résumé content isn't asserted anywhere — the config loader only checks the file
resolves). `load_vertical_config('grid_power_software')` still loads the re-tilted résumé; the new
aviation résumé file reads + parses. The aviation config that references it lands in Block 3.

**Verified:** full Python gate green — ruff format/check, **233 pytest**, lint-imports, mypy, lock.
Both résumés load through the config path. **No `src/` change.**

**Next:** Block 3 — `config/verticals/aviation_software.yaml` (matching_profile → aviation résumé +
domain vocabulary, Stage-A scope, Stage-B prefilter) + a `test_vertical_config.py` aviation case.
**STOP here for Hayden to commit + PR.**

**Branch:** `feat/resume-retilt` (off `main` @ the merged Block-1 PR).

---

## 2026-06-22 — Phase 7 · Block 1: aviation employer seed + ATS resolution (config/data only)

**Did:** Curated + ATS-resolved the **aviation vertical** employer universe — the data half of the
D-004 architecture test (config + curation only, zero `src/` change). Hayden had seeded 16 partial rows
(names + category); I completed the columns and broadened to **36 employers** across every aviation
sub-domain (airlines · avionics · OEM/manufacturers · GDS/airline-IT · flight-data/analytics ·
ATM/infrastructure · eVTOL/autonomy · travel-tech SaaS).
- **Resolution = live probing** (same pass as grid, D-015): probed Greenhouse/Lever/Ashby slugs, fetched
  careers pages to fingerprint the ATS, and POSTed candidate Workday `cxs` endpoints. Result:
  **8 verified/fetchable** — GH (OAG `oagaviationworldwide`, FLYR `flyr`), Lever (Shield AI `shieldai`,
  391 open), Ashby (Beacon AI `beaconai`), Workday (Boeing `boeing:wd1`, 1168; Collins/RTX
  `globalhr:wd5`, 4161; Airbus `ag:wd3`, 2000; Wisk `wisk:wd108`, 24) — **6 detected** (iCIMS: Alaska/
  SITA/Joby; Avature: Delta; SuccessFactors: JetBlue; Oracle: Honeywell) — **22 layer2** (Phenom/Radancy
  portals + custom JS-rendered sites).
- **Caught a name collision:** the Greenhouse `archer` board is **Archer Veterinary Clinic**, not Archer
  Aviation — exactly why we probe-and-verify instead of guessing slugs. Archer Aviation → custom/Layer 2.
- Regenerated `data/seed/employers_seed.csv` deterministically (preserved the 54 grid rows byte-for-byte,
  `csv.writer` for the new aviation block). Updated `data/seed/README.md` with the aviation status block.

**Decisions:** none new (executes D-002/D-004/D-015/D-017/D-018; ADR D-046 lands with the Block-4 result).
Mega whole-company Workday boards (RTX/Airbus/Boeing, ~7300 mostly non-US/senior postings) kept verified —
the Stage-A scope gate + Stage-B US/level pre-filter cut them to the early-career US slice, same as grid's
GE Vernova. **Heads-up for Block 4:** that ~7300-posting first fetch + its Stage-A extraction backlog will
likely run a few dollars more than the "couple dollars" estimate — I'll surface concrete counts after
`vja-run` and confirm before the paid extract/match.

**Tests:** updated `test_employers_import.py` — totals auto-adapt; bumped the fetchable assertion (24→32,
Workday 15→19) and added `test_aviation_vertical_is_fetchable_without_code_change` (aviation resolves to
8 fetchable via the same code path, no per-vertical branch). These pin data counts, not new src behavior.

**Verified:** full Python gate green — ruff format/check, mypy (37 files), lint-imports (1 kept/0 broken),
**233 pytest** (+1), `uv lock --check`. **No `src/` change** (the architecture test holds so far).

**Next:** Block 2 — re-tilt both resumes (aviation: skills/interests + flight-delay project; grid:
Strait-of-Hormuz project + energy skills/interests). **STOP here for Hayden to commit + PR.**

**Branch:** `feat/aviation-seed` (off `main` @ PR #31).

---

## 2026-06-22 — Corpus location repair + stale-match cleanup (D-043 · WS5) · Branch B

**Did:** Built + ran the one-time repair that fixes the corpus Branch A's clobber already damaged.
- **`src/vja/repair.py`** (`vja-repair` CLI, new top-layer module): per vertical, re-derives `location`
  from each posting's `raw_payload` (GH `location.name` / Lever `categories.location` / Ashby
  `location` / Workday `locationsText`), writes it L1-authoritatively (a null snapshot never nulls a
  model fill), recomputes + persists `in_scope` from `passes_prefilter` on the effective location, then
  deletes matches whose posting now fails Stage B. Idempotent, offline (no LLM). Repo helpers:
  `postings_for_repair` + `apply_location_repair` (`db/postings.py`), `delete_matches_failing_scope`
  (`db/matches.py`). `repair` added to the import-linter top layer.
- **Ran it on `data/vja.db`** (backup at `data/vja.db.pre-repair.bak`): postings=2335,
  **locations_repaired=349**, in_scope **42 true / 444 false**, **matches_deleted=48**. Blank-location
  rate on extracted-open rows went **84/266 + 48/191 + 4/22 → 0/0/0**.
- **Verified (sqlite spot-checks):** the 3 named foreign roles (Mumbai/Bangalore/Mexico City) are
  `in_scope=0` with no match; **0** matched postings have `in_scope≠1`; every matched yes/maybe role is
  now US. The 444 in_scope=False split: 312 senior/mid level + 132 genuinely foreign (Hong Kong, London
  UK, Pune, Singapore…).

**Also (D-045, found during live dashboard testing):** "rejected never shown" made *Cleaned* collapse
onto *Matched* once the corpus is fully assessed (both = 8). Redefined **Cleaned = the whole in-scope
set, every verdict incl. `no`** (the objective US-software job list, profile-independent); *Matched*
unchanged (this résumé's relevant verdicts). `open_postings_with_match_quality` drops the always-hide-`no`
clause; the `cleaned` branch now applies no verdict filter. Live: matched=8, **cleaned=41** (8 maybe + 33
no). Ran `vja-match` (1 straggler, $0.0136). `no` stays hidden from *Matched* + the digest (D-037).

**Decisions:** D-045 (Cleaned = whole in-scope set incl. rejected; amends D-043). The repair itself
executes D-043. Tests: `test_repair.py` + updated `test_dashboard_query.py`/`test_api.py` (cleaned shows
rejected; matched hides it).

**Verified:** full Python gate green — ruff, mypy (88 files), lint-imports (1/0), **232 pytest**, lock.
Frontend 14 vitest green (cleaned now renders `no` rows with their badge — kept, removable later).
**Heads-up:** a stale `vja-api` (started before these changes) serves the old API — **restart it**.

**Known residuals (coarse-gate, undecidable from a bare token):** (A) foreign cities whose 2-letter
code = a US state code pass in_scope but Sonnet rejects — `Bogota, CO`, `Buenos Aires, AR` (×2); (B)
bare US city w/o state code dropped — `Chicago` (×5). Both small; possible follow-up (city list).

**Branch:** `fix/corpus-location-repair` (off merged `main` @ PR #30). `data/vja.db` mutation is local
(gitignored); the commit is the repair code + tests + this log.

---

## 2026-06-22 — Location-blind pipeline fix + dashboard two-view redesign (D-043, D-044) · Branch A

**Did:** B2 use exposed foreign roles (Mumbai/Bangalore/Mexico City) rated yes/maybe + confusing
"unassessed"/"rejected" toggles. Root cause found: **L2 extraction was overwriting the L1 `location`
with `null`** (`save_extraction` wrote every column unconditionally; Haiku returns null location),
which blinded Stage B (coarse keep-null) *and* Sonnet (`_posting_text` omits a null location). Fixed
the pipeline + redesigned the dashboard. This is **Branch A** (code+tests+docs); the corpus repair +
re-match is Branch B (WS5, not yet done — `data/vja.db` still holds the stale matches).
- **WS1 — location L1-authoritative:** `save_extraction` now fills `location` only when the stored
  value is NULL, never overwrites a non-null L1 value (mirrors the `source_updated_at` guard).
- **WS2 — persisted `in_scope`:** new `postings.in_scope` bool (migration `d30501b4c8ab`), stamped at
  extraction from `passes_prefilter` on the *effective* L1-authoritative location (so a clobbered-null
  model read can't fake a pass). `ExtractionCandidate` now carries `location`; `run_extraction` takes
  `PrefilterConfig` (CLI + nightly callers updated).
- **WS3 — dashboard two-view:** `open_postings_with_match_quality` floors on `in_scope IS TRUE`, always
  hides `no`, and takes a single `cleaned` bool (Matched default / Cleaned). API `view` enum replaces
  `include_unassessed`/`include_rejected`. Frontend: segmented Matched/all-cleaned control (replaces
  the two checkboxes), `api.ts`/`App`/`Controls` + vitest updated.
- **WS4 — prefilter collision:** `_NON_US_COUNTRY_NAMES` override so "Bengaluru, India, IN" /
  "Cordoba, Argentina, AR" fail Stage B despite IN/AR doubling as US state codes; omits country names
  that are US places (New Mexico / Georgia); bare codes w/o a country name ("Munich, DE") stay a
  residual Sonnet backstops.

**Decisions:** D-043 (L1-authoritative location + persisted `in_scope` + dashboard Matched/Cleaned,
supersedes D-041's additive toggles), D-044 (Stage-B non-US country override). Per this session's
sign-off (delete-and-rematch for repair; persist the flag; drop the rejected axis).

**Verified:** full Python gate green — ruff format/check, mypy, lint-imports (1 kept/0 broken), **230
pytest** (+4 new: location-not-clobbered, in_scope-on-effective-location, prefilter override ×2), `uv
lock --check`. Frontend lint/typecheck/**14 vitest**/build green. Migration round-trips on a clean DB;
`alembic check` clean. (Downgrade on the *populated* `data/vja.db` hits a SQLite-batch FK artifact
shared by the existing postings migrations — upgrade is the only gated path.)

**Next:** **Branch B (WS5)** — tested idempotent repair CLI: re-derive `location` from `raw_payload`
per ATS (GH `location.name` / Lever `categories.location` / Ashby `location` / Workday `locationsText`),
recompute `in_scope`, delete matches whose posting now fails Stage B, then `vja-match`. Then the data
spot-checks (no foreign matched rows; the 3 named rows in_scope=false + no match). Open thread
(unchanged): grandfathered `db→fetchers` edge refactor.

**Branch:** `fix/location-pipeline-and-dashboard` (off merged `main` @ PR #29).

---

## 2026-06-21 — Phase 6 · Block B2: React dashboard table over `/api/postings` (D-042)

**Did:** Built the read-only dashboard SPA — the **pull** surface (D-010) — the repo's first frontend. Consumes B1's
`GET /api/postings` verbatim and renders the full D-041 surface against live `data/vja.db` (483 in-scope open / 89
matches).
- `frontend/` (new): Vite + React + TS, no router/state lib. `src/api.ts` (typed client mirroring B1's
  `PostingRow`/`PostingsResponse`; `postingsPath` is the one home for the toggle→param mapping), `theme.css`
  (DESIGN.md tokens as CSS custom properties — dark-only, one accent), `App.tsx` (resolves vertical via
  `/api/verticals`, fetch-on-toggle, loading/error/empty states), `components/{Controls,PostingsTable,Verdict}`.
  Table: company · title→apply · location · activity date · match (verdict badge + mono score, color-coded; dim `—`
  when unassessed). Row expands to fits/gaps/rationale (3px accent spine).
- Backend (`src/vja/api/app.py`): added `CORSMiddleware` (GET-only, `VJA_CORS_ORIGINS`, default `:5173`), `GET
  /api/verticals` (→ new `active_verticals` in `db/profiles.py` so no slug is hardcoded), and an optional
  `frontend/dist` `StaticFiles` mount (prod same-origin; guarded so tests/CI without a build are unaffected).
- Gates (the D-042 precedent): `frontend` CI job (Node 24 → eslint + `tsc --noEmit` + `vitest run`) + a path-filtered
  `frontend-checks` pre-commit hook. `frontend/{node_modules,dist}` gitignored; `package-lock.json` committed.
- Tests: +14 vitest/RTL (`api`, `Controls`, `PostingsTable`, `App`) pinning param mapping, control emission, render
  rules (no fake score for unassessed, rejected dimming, expand reveals detail), refetch-on-toggle. +2 Python
  (`test_api.py`: CORS header, `/api/verticals`).

**Decisions:** D-042 — stack (Vite/React/TS), styling (plain CSS vars per DESIGN.md, no Tailwind), frontend tests =
Vitest+RTL as a path-filtered gate, serving (Vite dev + CORS / prod StaticFiles), `/api/verticals` to avoid a
hardcoded vertical. Bumped Vitest 2→3 (v2 nests Vite 5, clashing with the top-level Vite 6 plugin types). All per
this session's sign-off.

**Verified:** frontend `npm run lint` + `typecheck` + `test` (14) green, `npm run build` clean (148.9 kB JS gzip
47.8). Python `test_api.py` green (11). Full gate run (Python + e2e against live DB) = next task.

**Next:** Phase 7 (aviation vertical — config + curation, any forced code change is a defect). Open thread
(unchanged): grandfathered `db→fetchers` edge refactor.

**Branch:** `feat/dashboard-react-table` (off merged `main`).

---

## 2026-06-21 — Phase 6 · Block B1: dashboard read-only API (D-041)

**Did:** Built the FastAPI read API the React table (B2) will consume. Planning surfaced that the dashboard's
"full open set" (D-030) was underspecified — `postings` holds the *raw* open set incl. out-of-scope roles
(Stage-A scope gate D-034 is on-the-fly, never stored; `extracted_at IS NOT NULL` is the only durable in-scope
marker). Resolved with three tiers and **D-041**.
- `src/vja/db/postings.py`: new `open_postings_with_match_quality(engine, vertical, profile_id, resume_version,
  *, cutoff, by_first_seen, include_unassessed, include_rejected)` + `DashboardPosting`. Floors on Tier 2
  (`extracted_at IS NOT NULL`), LEFT-JOINs `matches` on `(profile_id, resume_version)`. Two axes: match-status
  (matched-only default; `include_unassessed` → null-match rows; `include_rejected` → un-hide `no`) × recency
  (`activity_window_clause` / first_seen / all). **Retired** the A2 `open_postings_in_window`/`OpenPosting`
  (caller-less — backfill uses `postings_needing_match(since=)`).
- `src/vja/api/` (new top layer): `create_app()` + `GET /api/health` and `GET /api/postings`
  (`vertical`/`window`/`profile_id`/`include_unassessed`/`include_rejected`), Pydantic `PostingRow`/envelope,
  `_resolve_profile` thin default (404 none/unknown, 409 ambiguous). `vja-api` CLI (uvicorn, localhost).
- `models.RELEVANT_VERDICTS` lifted out of `digest/assembly.py` → one home for the digest + dashboard.
- import-linter: `api` added to the top layer (`nightly | api`).
- Tests: `test_dashboard_query.py` (DB-level: tiers, both axes, recency — folds in the retired A2 window tests)
  + `test_api.py` (HTTP: param mapping, profile resolution, health). Deleted `test_postings_window.py`.
- Docs: D-041; INVARIANTS dashboard section; fixed stale docs/11 §3.3 backfill cap (14d→5d) + marked §2 seam
  adopted.

**Decisions:** D-041 (per Hayden). Dashboard = in-scope (T2) universe, matched-default (T3); `no` hidden by
default (mirrors digest D-037); LEFT-JOIN over reuse+merge. Key clarification: the 5-day cap (D-039) is a
*matching/backfill* cost lever — the dashboard is read-only and never matches (D-005), so its window is free and
decoupled from the cap.

**Verified:** new tests pass (18); full gate run next.

**Next:** Phase 6 · B2 (React table over `/api/postings`) — `DESIGN.md` ("terminal dev-tool, dark") is the UI
spec; wire CORS for the dev server there. Open thread (unchanged): grandfathered `db→fetchers` edge refactor.

**Branch:** `feat/dashboard-read-api` (off merged `main`).

---

## 2026-06-21 — Comprehension-debt guards: enforced import layering + INVARIANTS registry (D-040)

**Did:** Interlude before Phase 6 · B1, prompted by Hayden feeling he and Claude were losing the thread.
Diagnosis from a real survey: the *code* is healthy (~4.1k LOC, max file 377, clean layered DAG, ~1:1 tests) —
what grows unbounded is the *context to change it safely* (39 ADRs, 840-line WORKLOG). Built two cheap guards:
- **#1 Import contract (`import-linter`).** Encoded the real dependency stack as a layered contract in
  `pyproject.toml` (`nightly → pipeline/extract/match/digest → fetchers/verticals → db → helpers → models`);
  wired `uv run lint-imports` into pre-commit + CI after mypy. Verified it has teeth (breaks on a synthetic
  removal of the exception). Setup surfaced a back-edge nobody knew about: `db.employers → fetchers.registry`
  (`SUPPORTED_ATS_TYPES`) — grandfathered as one documented `ignore_imports` line; new `db→fetchers` edges fail.
- **#2 `docs/INVARIANTS.md`.** Derived "what's true now" registry, mined from D-001…D-039, each rule → its ADR.
  Caught the live example: backfill cap is **5 days** (D-039), not D-024's original 2 weeks. Linked read-first
  from `CLAUDE.md` doc map; added a discipline rule (ADR that changes a live rule must update INVARIANTS same session).

**Why:** convert "good architecture by luck/discipline" into machine-guaranteed structure, and give both Hayden
and each fresh agent session a single current-truth doc instead of replaying 39 ADRs. See D-040.

**Verified:** full gate suite green — ruff format/check, mypy, `lint-imports` (1 kept / 0 broken, 86 deps),
211 tests, `uv lock --check` clean.

**Next:** Phase 6 · B1 (FastAPI read API: recency toggles→cutoffs + LEFT-join match quality on the
`(vertical, profile_id)` seam). Open thread: optionally refactor the grandfathered `db→fetchers` edge (inject
supported set from orchestration layer) — deferred to keep this chunk tight.

**Branch:** `chore/import-contract-and-invariants` (off the merged A2 state).

---

## 2026-06-21 — Phase 6 · Block A2: recency-window query + index + signup backfill (D-039)

**Did:** Consumed A1's `source_updated_at` to build the dashboard's recency prerequisite + the D-024
signup backfill — the two consumers D-030 said would share one date predicate.
- `db/postings.py`: `activity_window_clause(cutoff)` (the one home for
  `COALESCE(source_updated_at, first_seen_at) >= cutoff`), `OpenPosting` dataclass (match-free
  dashboard row), and `open_postings_in_window(vertical, *, cutoff, by_first_seen)` — open postings
  in a window, newest-activity-first, no match join. `cutoff=None` → all open; `by_first_seen=True`
  → the "new today" basis (first_seen only = calendar midnight UTC, so it equals the digest); else
  the activity predicate (week/2-week toggles + backfill).
- `db/matches.py`: `postings_needing_match` gains a keyword-only `since=` that ANDs in
  `activity_window_clause` (default `None` = nightly, byte-identical). This is what bounds backfill.
- `db/schema.py` + migration `f7164d547f15`: `ix_postings_status_source_updated` on
  `(status, source_updated_at)`. Applied + round-tripped on local `vja.db`.
- `match.py`: extracted `run_matching`'s per-profile loop into shared `_match_profile`
  (`since`/`trigger` params); added `run_backfill(vertical, profile)` (5-day cap,
  `trigger=backfill`, idempotent) + `vja-backfill --vertical V [--email X]` CLI (registered in
  pyproject). Nightly matching behavior unchanged.

**Decisions:** D-039. Per Hayden's sign-off: (1) **match-free shared primitive** (dashboard layers
verdict/score in B1, keeping the docs/11 `(vertical, profile_id)` seam in the API layer; backfill
reuses the bare window); (2) **flexible cutoff, not a rigid 4-toggle enum** (backfill's 5d isn't a
toggle value); (3) **backfill = 5 days, not 14** — **amends D-024** and decouples it from the
dashboard's 14d "Two weeks" toggle (they share only the predicate now); (4) **nightly stays
uncapped** — the digest's `first_seen_at` window already keeps old backlog out of the inbox, so the
cap is the backfill's job alone; (5) **"new today" = calendar midnight UTC**.

**Tests:** +9 (202→211). `test_postings_window.py` (activity basis + fallback, new-today first_seen
basis, all-open, newest-first order, vertical scoping, open-only, dashboard columns).
`test_backfill.py` (5d-window matching, `trigger=backfill`, idempotency, + a direct
`postings_needing_match(since=)` repo test). `test_matching_run.py` unchanged + green (pins the
`_match_profile` refactor preserved nightly behavior).

**Verified:** ruff + format + mypy(strict) clean; **211 passed, 8 deselected**; `alembic check`
clean + `downgrade -1`/`upgrade head` round-trip. Smoke on local `vja.db`: window sizes monotonic
(all_open 2175 → last_1d 4 → new_today 4); `vja-backfill --help` wired.

**Next:** Phase 6 **B1** — FastAPI read API (`(vertical, profile_id)`-parameterized per docs/11),
mapping the recency toggles → `open_postings_in_window` cutoffs + LEFT-joining match quality; then
**B2** — the Vite/React/TS table served by FastAPI.

---

## 2026-06-21 — Phase 6 · Block A1: ATS date normalizer + `postings.source_updated_at`

**Did:** Built the deferred D-030/D-024 date infra — one normalized, queryable ATS activity date, the
dashboard recency toggles' (A2/B) backend prerequisite.
- `src/vja/dates.py` (new): `normalize_ats_date(str|None) → datetime|None`. ISO 8601 (offset/`Z`/naive→UTC/
  date-only) + epoch sec/millis digit-strings (Lever) → tz-aware UTC; unparseable → `None`, never raises.
  Resolves the parked DRW malformed-`posted_at` row (it now normalizes to `None`).
- `db/schema.py` + migration `13c2203d963b`: new nullable `postings.source_updated_at` (`UTCDateTime`).
  Hand-fixed the autogen to render the custom type as `sa.DateTime(timezone=True)` (matches the initial
  migration; the autogen emitted an un-imported `vja.db.schema.UTCDateTime` ref). Applied to local `vja.db`.
- `db/postings.py`: `insert_posting`/`bump_last_seen`/`update_changed` take a keyword-only
  `source_updated_at` (bump/update write it only when non-None — never null a good value);
  `save_extraction` fills it via `CASE WHEN source_updated_at IS NULL` (L1-authoritative).
- `pipeline.py`: normalizes `posting.updated_at` and passes it to all three L1 write paths (so the unchanged
  `bump` path refreshes it too — self-heals the existing GH/Lever/Ashby corpus next run).
- `extract.py`: passes `normalize_ats_date(fields.posted_at)` to `save_extraction` (fills Workday's date).

**Decisions:** D-038. Per Hayden's sign-off: (1) **L1 `updated_at` authoritative, L2 `posted_at` fills only
when NULL** (vs literal "most recent" — better data quality, dialect-portable); (2) **refresh on every
sighting** incl. the unchanged path, guarded non-NULL, which also self-heals the corpus. Accepted limitation:
existing Workday rows (already extracted, no L1 date) stay NULL → dashboard falls back to `first_seen_at`
(the documented Workday weak spot).

**Bug found + fixed (probe before sign-off):** a bare digit string like `"2026"` (a plausible LLM
`posted_at`) was parsed as epoch-seconds → **1970** — a garbage date is worse than NULL (NULL falls back to
`first_seen_at`; 1970 reads as ancient and drops out of every recency window). Fixed with a posting-era
sanity guard in `_from_epoch` (reject if the resolved year ∉ [2000, 2100]) + a regression test.

**Tests:** +26 (176→202). `test_dates.py` (ISO offset/`Z`/naive/date-only, Lever ms + epoch sec, empty,
malformed/DRW regression, **implausible-epoch guard**, surrounding whitespace). `test_pipeline.py` (insert
persists normalized date; no-date→NULL; bump self-heal/backfill; content-change refresh; later-null never
clobbers). `test_extraction_run.py` (extraction fills only when NULL; never overrides an L1 date).

**Verified:** ruff + format + mypy(strict) clean; **202 passed, 8 deselected**; `alembic check` clean.

**Next:** A2 — `open_postings_in_window` query helper (D-030 criterion: `source_updated_at` in-window OR
`first_seen_at` fallback; *new today* = `first_seen_at`) + its `(status, source_updated_at)` index, then the
onboarding backfill (D-024, `trigger=backfill`, ≤14d cap). Then Phase 6 B1 (FastAPI read API) / B2 (React).

---

## 2026-06-20 — Phase 6 prep · multi-user & hosting migration ledger (doc-only)

**Did:** Added `docs/11-multi-user-and-hosting.md` — a *living checklist* (not a design doc) for the
eventual D-025 hosting/Postgres + multi-user cutover. Three working sections: (1) **already portable** (DB
D-025, runtime D-031, cost model D-005, matching D-006, identity/resume seams D-027/D-033 — linked so they
aren't re-derived under cutover pressure); (2) **seams to preserve** — chiefly the rule that the **Phase-6
dashboard API is `(vertical, profile_id)`-parameterized**, so adding auth later is a filter, not a rewrite;
(3) **deferred work enumerated** — security/PII (flagged highest-stakes), auth/identity, cost/abuse guards
(signup backfill is the first place user action drives LLM spend), email deliverability, live
migrations/observability. Added it to the CLAUDE.md doc map.

**Why:** Hayden flagged that lots of design is deferred to an approaching cloud migration with no written
plan. Turning "a lot goes into it" into an enumerated, trackable ledger is cheap and prevents single-user
assumptions from hardening silently — discipline is *document the seams now, build the machinery at the
trigger*; kept honest with the kill criterion (no speculative scaffolding).

**Decisions:** none new (no ADR — this is a ledger over existing decisions). Adopted-but-unrecorded
convention surfaced for Phase 6: the read API is `(vertical, profile_id)`-parameterized (will land with B1).

**Tests:** none (doc-only).

**Next:** in-depth plan of **A1** (normalize → persist the ATS activity date: `postings.source_updated_at`
+ migration + per-ATS normalizer; closes the parked DRW malformed-`posted_at` fix), then code.

---

## 2026-06-19 — Phase 5 · Block 4: digest rationale + nightly extract→match→send + recipient→profiles

**Did:** Composed the Layer-2 pieces (5.1–5.3) into the nightly loop and put the match rationale in the
inbox — Phase 5 is now end-to-end. Three wiring seams (D-037):
- `digest/assembly.py`: `build_digest` is now per **(vertical, profile)** — INNER-JOINs `matches` on
  (posting, profile, resume_version) gated to verdict ∈ {strong_yes, yes, maybe}, ordered by `score`
  desc. `DigestPosting` gains verdict/score/rationale/fits/gaps; `DigestContents` gains `recipient`.
  `last_sent_at` now keys on (vertical, **recipient**) so each profile's window is independent.
- `digest/render.py`: new-role lines render `[verdict · score]` + the one-line `rationale` (text + HTML);
  `fits`/`gaps` go into the `contents` audit JSON but **not** the body (D-037 scannability).
- `digest/send.py`: `send_digest(engine, vertical, profile, …)` → recipient = `profile.user_email`;
  `send_main` loops verticals → `active_profiles`. `send_email` takes an explicit recipient (alert path
  still uses `config.recipient`). `DigestConfig.recipient` redocumented as the **ops/alert** address.
- `nightly.py`: `run_nightly` = pipeline → per config-vertical `run_extraction`+`run_matching`
  (`_default_layer2`, injectable as `run_layer2` for offline tests; one Anthropic client shared) →
  `send_digest` per active profile. Per-vertical isolation around the Layer-2 pass; LLM totals written to
  the run row via `update_llm_metrics`; `NightlyResult` + the printed summary carry extracted/matched/cost.
- `db/pipeline_runs.py`: `update_llm_metrics` (the columns `finish_run` had stubbed at 0).

**Decisions:** D-037. Resolved with Hayden: (1) digest hides `no` + unmatched, sorts by score; (2) body
carries verdict+score+one-liner (fits/gaps audit-only); (3) **three wiring items only** — `posted_at`
normalization (D-030) + new-user backfill (D-024) stay deferred to the backfill block (docs peg that work
to Phase 5 *because backfill needs it*; the nightly digest is a diff and reads no `posted_at`). DRW
malformed-date fix stays parked there too.

**Tests:** +5 net (172→176) — `test_digest_render.py` (verdict/score/rationale in body; fits/gaps
audit-only; closures carry no match fields), `test_digest_assembly.py` (match-gating drops `no`/unmatched;
score-desc order; per-recipient `last_sent_at`; window/closures), `test_digest_send.py` (recipient =
profile email; per-profile rows), `test_nightly.py` (composition via injected `run_layer2`; rationale in
the delivered body; LLM totals on the run row), `test_nightly_alert.py`/`test_digest_send_e2e.py` updated
for the new signatures.

**Verified:** ruff + format + mypy(strict) clean; **176 passed, 8 deselected**; `alembic check` clean
(no DDL); eval still collects (2 match evals). Live `vja-nightly` smoke pending (Hayden).

**Next:** Phase 6 — dashboard (read-only FastAPI + React table with recency toggles, D-030). Still open:
record the deferred onboarding-backfill decision + build it (with the D-030 `posted_at` normalize→persist,
which the backfill needs first) and the parked DRW date fix; consider the Batches API for the backfill burst.

---

## 2026-06-19 — Phase 5 · Block 3: Stage-B pre-filter + LLM matching (Sonnet, fits/gaps/verdict)

**Did:** Closed the two-stage filter (D-023) and wrote the first `matches` rows — the product's
actual output, a resume-match rationale per posting.
- `src/vja/prefilter.py`: `passes_prefilter(level, location, cfg)` — Stage B, pure/deterministic,
  no LLM. Drops only *confirmed* out-of-range postings (concrete `mid`/`senior` level, clearly
  non-US location); `unknown`/null/`remote` pass (coarse gate, the LLM refines — same philosophy as
  Stage A). Geo = US-signal allowlist (postal codes + full state names + `United States`/`USA`/
  `America`/`remote`), whole-word + case-insensitive. `work_auth` is **not** gated (no config
  values, candidate auth not encoded) — passed to the matcher as a signal.
- `src/vja/match.py`: `MatchResult` (pydantic: verdict/score/fits/gaps/rationale) →
  `client.messages.parse(model="claude-sonnet-4-6", thinking=adaptive)`; `match_posting`
  (returns rationale + cache-aware metered cost), `run_matching` (per active profile: Stage A
  `in_scope` on title ∧ Stage B over extracted fields ∧ not-yet-matched → strong model → persist;
  per-posting isolation, cost summed), `vja-match` CLI. **Resume + instructions are the cached
  prefix** (`cache_control` ephemeral); only the per-posting structured fields are volatile.
- `src/vja/db/matches.py`: `postings_needing_match` (open ∧ extracted ∧ no `matches` row for
  (posting, profile, resume_version) — idempotency) + `save_match`. No DDL — `matches` pre-existed.
- Added `vja-match` script; `load_dotenv()` in `match_main` before the client (the 5.2 lesson).

**Decisions:** D-036 (Stage-B prefilter + Sonnet matching, fits/gaps/verdict/score, prompt-cached
resume, eval-gated). Resolved with Hayden: **Sonnet not Haiku** — matching is judgment / the
user-visible trust-critical output, extraction is mechanical (D-005 tiering); cost is bounded by
the gates (~$2 one-time backfill + pennies/night), so it's a quality call, not a cost one. Stage-B
+ matching ship as **one block**. Clarifies D-023's "Stage B writes `matches.score`": Stage B is an
**in-memory filter** (no row for non-survivors, since `verdict` is NOT NULL); **`score` is the LLM's
0–100 output**, persisted with the rest of the rationale.

**Tests:** +15 — `test_prefilter.py` (unit: early-career/US passes; senior/mid/non-US drop;
unknown/remote pass; config-driven levels), `test_match.py` (unit, faked client: result→column
mapping, cache-aware cost math, cached-prefix shape, no-parse failure), `test_matching_run.py`
(integration: selects only open+extracted+Stage-A+Stage-B+unmatched; skips out-of-scope/unextracted/
senior/non-US/other-vertical/already-matched; idempotent; per-posting isolation; multi-profile),
opt-in `eval` (`test_match_eval.py`, real Sonnet: structural + obvious-yes + obvious-no — D-020 gate).

**Verified:** ruff + format + mypy(strict) clean; **172 passed, 8 deselected**; `alembic check` clean
(no DDL); eval collects (2 new match evals). Live smoke (Hayden runs `vja-match`) pending.

**Next:** P5.4 — wire the rationale into the digest (verdict/fits/gaps per new posting) and compose
extract + match into `vja-nightly` (D-027 recipient → profiles rides along).

---

## 2026-06-19 — Phase 5 · Block 2: LLM extraction (Haiku), cached by content_hash

**Did:** First LLM code in the system — Layer-2 extraction of structured fields from in-scope postings.
- `src/vja/extract.py`: `ExtractedFields` (pydantic) → `client.messages.parse(model="claude-haiku-4-5")`;
  `extract_posting` (returns fields + metered cost from `usage`), `run_extraction` (selects in-scope
  unextracted, per-posting isolation, persists, sums cost), `vja-extract` CLI. **All-LLM**, **synchronous**.
- `src/vja/db/postings.py`: `postings_needing_extraction` (open ∧ `extracted_at IS NULL`; in-scope filtered
  by the caller), `save_extraction`; **`update_changed` now nulls `extracted_at`** on a content change
  (cache invalidation). Added `ExtractionCandidate`.
- `src/vja/fetchers/workday.py`: `fetch_detail` — pulls a posting's cxs detail (`jobDescription` + real
  `startDate` + structured `country`) so Workday gets full extraction (the lazy Layer-2 fetch D-032 named).
- Added `anthropic` dep; `vja-extract` script; `ANTHROPIC_API_KEY` in `.env.example`.

**Decisions:** D-035 (Haiku cheap tier, all-LLM, sync, cached by content_hash, Workday descriptions via
cxs detail, geo filtering deferred to Stage B). Resolved with Hayden: all-LLM (hybrid saves rounding-error
since the description is sent either way); sync (latency in-process, batch discount not worth polling);
**pull Workday descriptions** after confirming the cxs detail endpoint live — scoped to in-scope + cached
it's ~500 one-time GETs, not the Layer-1 storm.

**Tests:** +12 — `test_extract.py` (unit, faked client: mapping, cost math, Workday-vs-raw source, no-parse
failure), `test_extraction_run.py` (integration: selects only in-scope-unextracted; out-of-scope/
already-extracted/other-vertical skipped; idempotent; content-change re-opens), opt-in `eval`
(`tests/eval/test_extract_eval.py`, real Haiku on a senior/US fixture — the D-020 gate).

**Verified:** ruff + format + mypy(strict) clean; **157 passed, 6 deselected**; `alembic check` clean (no
DDL — Layer-2 columns pre-existed); eval collects.

**Live run:** Hayden added `ANTHROPIC_API_KEY` and ran `vja-extract --vertical grid_power_software`.
First attempt failed 422/422 (`Anthropic()` auth resolves at construction time, and `extract_main` never
called `load_dotenv()` — every other CLI entrypoint does this inside its own `load_config()`/`main()`,
this one was missed). Fixed: `load_dotenv()` added to `extract_main` before `get_engine()`, matching the
`digest/send.py::load_config()` pattern. Re-run: **420/422 extracted, 2 failed, est_cost=$1.65** (in-scope
backlog was 422, not the ~1k originally estimated — Stage-A cuts harder than guessed; cost ran ~3x the
$0.55 estimate, worth re-baselining per-posting cost next time payload sizes are this large). The 2
failures are Layer-1 Workday `cxs` detail-fetch errors (403 on one tenant, 404 — posting likely closed
between list and detail fetch), not extraction bugs; per-posting isolation worked as designed. `pytest -m
eval` (1 passed) and full suite (157 passed) green post-fix.

**Spot-checked** extracted rows: Workday `stack` values (e.g. `Allen-Bradley`, `Triconex`, `RSLogix`)
prove the cxs detail fetch is feeding real description text, not just the list payload; `level` varies
sensibly; comp fields populate correctly when the posting states a range (Greenhouse/Lever ~33-50%, Workday
~12%) and stay null otherwise. **Known minor issue (logged, not fixed):** one row (DRW posting id 6) has a
malformed `posted_at` — Haiku appended a leaked `location` JSON fragment after the date
(`"...T12:24:44-04:00\n\n{\"location\": \"New York City\"}"`). 1/420 (0.24%), cosmetic today since
`posted_at` isn't parsed/joined anywhere yet — defer the fix to the Phase-6 date-normalization work (D-024),
which will need to sanitize/parse this field for the dashboard recency toggles anyway.

**Next:** P5.3 — Stage-B cheap pre-filter (level/location/work-auth + the geo filter) → strong-tier
matching/rationale (fits/gaps/verdict, Option 4) → `matches` rows + the matching eval gate.

---

## 2026-06-18 — Phase 5 · Block 1: profiles + vertical config + Stage-A scope gate (NO LLM)

**Did:** The deterministic foundation for Layer 2 — zero LLM cost, no schema change.
- `config/verticals/grid_power_software.yaml` — the first "a vertical is config" file (D-004):
  matching_profile (user_email + resume path + domain_vocabulary), the new `scope` section (Stage-A
  keyword lists), and `prefilter` knobs (consumed in 5.3). `config/verticals/profiles/hayden_grid_resume.md`
  (Hayden's real resume).
- `src/vja/verticals.py` — `load_vertical_config(key)` → validated `VerticalConfig` (resolves + reads
  the resume); `vja-load-profiles` CLI loads every `config/verticals/*.yaml`. Added `pyyaml` + `types-pyyaml`.
- `src/vja/scope.py` — `in_scope(title, scope)`: balanced whole-word, case-insensitive gate (≥1
  role_include AND no exclude), regex cached by keyword tuple. Pure; computed on-the-fly (no column).
- `src/vja/db/profiles.py` — `upsert_profile` (idempotent; `resume_version = sha256(text)[:12]`,
  new version → new active row, prior deactivated) + `active_profiles`. `docs/06` documents the `scope` section.

**Decisions:** D-034 (Stage-A = config-driven whole-word keyword gate, computed on-the-fly, no migration).
Resolved with Hayden: build the YAML loader (not a minimal bootstrap); balanced include+exclude gate;
on-the-fly (no `in_scope` column); real resume supplied now. Also D-033 (resume input abstracts to
`resume_text`; PDF = a future signup-flow adapter) — landed on a separate `docs/` branch from main.

**Tests:** +20 — `test_scope.py` (balanced/whole-word/none/role-required), `test_vertical_config.py`
(real config loads; missing-file/field/resume + key-mismatch errors), `test_profiles.py` (idempotent
upsert; versioning; vertical isolation).

**Verified:** ruff + format + mypy(strict) clean; **149 passed, 5 deselected**; `alembic check` clean
(no DDL — schema pre-provisioned Layer 2). `vja-load-profiles` created Hayden's active profile.
**Empirical Stage-A check** over the real grid universe: **400 of 1697 open postings in-scope (23%)**,
drops correct (senior/HR/ops) — a 77% cut to Layer-2 cost before any token is spent.

**Next:** P5.2 — LLM extraction (cheap tier, cached by `content_hash`) over Stage-A survivors + cost
metering + extraction evals (first Anthropic SDK code; model IDs via the `claude-api` skill).

---

## 2026-06-18 — Phase 4 · Block 2: onboard the verified Workday tenants (coverage 21 → 24)

**Did:** Config-only block — no new fetcher logic (D-004 again). Hayden pulled the real board URLs; I
live-verified the derived cxs endpoints, then updated the seed:
- **GE Vernova** activated — `Vernova_ExternalSite` (~2381 open, whole-company board).
- **BP** activated — `bpCareers` (~414); its board is slow, so bumped Workday `_TIMEOUT` 20 → 30s (generic).
- **Fluence** reclassified custom → Workday — `fluenceenergy:wd12:fluenceenergy-jobs` (~108); was a bonus 4th find.
- **Castleton** → custom/Layer 2: the `osv-cci.wd1` Workday proxy 422s the cxs API (board renders, no clean JSON).
- **Enverus** → jobvite (powered-by tag; Tier-C, no fetcher yet); **Aurora** unidentified → stays Layer 2.

**Decisions:** D-032 extended with the P4.2 onboarding + the reusable finding that `osv-` Workday hosts don't
expose the cxs API (→ Layer 2). Coverage now **24/54 fetchable** (9 Tier-A + 15 Workday).

**Tests:** updated `test_employers_import` fetchable 21 → 24, Workday 12 → 15. Existing Workday unit/live tests
unchanged (no fetcher-logic change).

**Verified:** ruff + format + mypy(strict) clean; **126 passed, 5 deselected**; `alembic check` clean. Live re-verify
through the real fetcher (GE Vernova 2381 paginated fully, Fluence 109; URLs well-formed). **End-to-end on a throwaway
DB** (kept prod's baseline clean): import → `vja-run` = **24 employers, 0 failures, 4597 postings, 1:47** (BP's slow
board fine under 30s; GE Vernova's 120 pages + completeness guard held). Re-imported seed into **prod** (config only,
no fetch) so the next scheduled nightly picks up the 3 new tenants.

**Heads-up:** that next nightly's `vja-run` will add ~2900 postings (GE Vernova 2381 + BP 414 + Fluence 108) to the
one-time Workday baseline digest; steady state after is small diffs. **Next:** P4.3 — generic pipeline-level
mass-closure guard (defense-in-depth on top of the fetcher's paginate-or-fail).

---

## 2026-06-17 (later still) — Phase 4 · Block 1: generic Workday `cxs` fetcher (coverage 9 → 21)

**Did:** Built the one generic Workday fetcher that lights up the 12 verified Workday tenants — the biggest
single coverage win.
- Probed PJM live first to capture the real cxs response → fixture `tests/fixtures/workday_pjm_jobs.json`,
  and confirmed the public apply-URL form (`{host}/{site}{externalPath}`, no locale segment) resolves.
- `src/vja/fetchers/workday.py` — `WorkdayFetcher`: **POST** the cxs `/jobs` endpoint, **paginate by offset
  until `total` is reached, fail (never return partial) on any page error or short tally** (fetcher-level
  false-closure guard). **List-only** mapping (`description=None`; deferred to a lazy Layer-2 fetch):
  `external_id = externalPath`, `apply_url` built from the cxs host+site+path, `location = locationsText`,
  `updated_at = None` (Workday's `postedOn` is relative text). Registered `AtsType.WORKDAY` in the registry.
- Parked the 3 `detected` tenants (BP, GE Vernova `SITE_TBD`; Castleton prefix) → `status=proposed` in the
  seed until P4.2 verifies their endpoints, so only the 12 verified tenants fetch.

**Decisions:** D-032 (Workday list-only + paginate-or-fail; the 3 detected parked). Confirmed with Hayden:
list-only (defer description cost to where Layer 2 uses it; accept that description-only edits aren't tracked);
park the unverified tenants for a clean nightly run.

**Tests:** +12 — `tests/unit/test_workday.py` (fixture mapping incl. derived apply_url; multi-page pagination
assembles all pages; truncated fetch → `FetchError` not partial; mid-pagination error → raise; empty board → [];
500/non-JSON/missing-`jobPostings`/missing-`total`/missing-`externalPath`/non-cxs-endpoint all → `FetchError`),
registry test extended (WORKDAY resolves; unsupported case moved to iCIMS), `test_employers_import` fetchable
count 9 → 21 (12 Workday). Opt-in `tests/live/test_workday_live.py` (PJM shape).

**Verified:** ruff + format + mypy(strict) clean; **126 passed, 5 deselected**; live Workday smoke passed;
`alembic check` clean (no DDL). **End-to-end:** re-imported seed → `vja-run` = 21 employers, **0 failures,
1131 new postings**, 44s; stored Workday apply URLs well-formed (e.g. Vistra `…/vistra_careers/job/…`).

**Next:** P4.2 — onboard the 3 detected tenants (live-probe BP/GE Vernova/Castleton endpoints + revisit
Fluence/Enverus/Aurora) → coverage 21 → 24; then P4.3 — generic pipeline-level mass-closure guard.

---

## 2026-06-17 (later) — Phase 3 · Block 3: nightly scheduling (launchd) + `vja-nightly` (Phase 3 complete)

**Did:** Made the loop run unattended — the last Phase-3 piece.
- `src/vja/nightly.py`: `run_nightly(engine, *, now, config, resolve_fetcher, verify)` composes
  `run_pipeline(vertical=None)` (all verticals, one pass) then `send_digest` per
  `distinct_active_verticals`, aggregates a status, and on a **hard failure** emails an alert.
  `NightlyResult{status, run, digests, alerted}`. `_send_failure_alert` reuses `send_email` (a
  `SendError` there is logged, not raised — can't alert if Resend is down). `nightly_main` →
  `vja-nightly` console script; logs to stdout/stderr, exits 1 on hard failure.
- **Hard-failure trigger:** pipeline `failed`, or any digest send `failed`. Partial fetch failures
  are logged + in the alert body but don't themselves alert (anti-noise, same logic as D-028).
- `deploy/launchd/`: `com.vja.nightly.plist.template` (StartCalendarInterval 06:00, absolute
  `.venv/bin/vja-nightly`, `WorkingDirectory` = repo root so `.env`/`data/vja.db` resolve, logs →
  `logs/`), idempotent `install.sh`/`uninstall.sh` (sed-substitute `__WORKDIR__`, load/unload), and a
  README (prereqs, baseline-first note, install/verify/uninstall, failure behavior). Added `.env.example`.
- `pyproject.toml`: `vja-nightly` entry point.

**Decisions:** D-031 — launchd over cron (runs a job missed during sleep on wake; cron silently skips);
one-process `vja-nightly`; alert-email-on-hard-failure + logs; 06:00. Recorded the **portability**
principle (scheduler = swappable trigger; portable core = the command + env config + `VJA_DATABASE_URL`;
app logs to stdout/stderr so the trigger routes them; cloud cutover swaps `deploy/<platform>/`, not code).

**Tests:** +7 — `test_nightly.py` (integration: happy→sent+no-alert; failed send→`failed`+alert, 2 Resend
calls; pipeline failure→alert even when digest skips; empty universe→nothing sent) + `test_nightly_alert.py`
(unit: `_failure_summary` content; alert subject carries counts; alert swallows a `SendError`).

**Verified:** ruff + ruff-format + mypy(strict) clean; **115 passed, 4 deselected**; `alembic check` clean
(no DDL). Plist renders to absolute paths; scripts `chmod +x`; `.env.example` is tracked (not git-ignored).

**Phase 3 complete** (assemble → verify → send → schedule). **Next:** Phase 4 — generic Workday `cxs`
fetcher (D-026), ~9→24 of 54 employers. (Operational: run `vja-nightly` by hand once to absorb the 581-role
baseline, then `bash deploy/launchd/install.sh`.)

---

## 2026-06-17 — Phase 3 · Block 2: render + Resend send + `digests` row lifecycle

**Did:** Closed the loop downstream of P3B1's `DigestContents` — the bare digest now actually sends.
- `src/vja/digest/render.py`: `render_digest(contents) -> RenderedEmail{subject, html, text}` +
  `contents_to_dict` (JSON-safe audit blob for the `contents` column). Body shows **new** roles
  (company · title · location · verified apply link) and **closed** roles; **quarantined** postings
  are kept out of the user-facing body but recorded in the audit JSON. Vertical slug is humanized
  generically (`grid_power_software` → "Grid Power Software") — no per-vertical code (CLAUDE rule).
- `src/vja/db/digests.py`: `create_pending` / `mark_sent` / `mark_failed` — mirrors the
  `pipeline_runs` repo (open `Connection`, caller commits per-txn). `pending` row carries full
  contents *before* the send; finalize flips to `sent` (+`sent_at`) or `failed` (+`error`).
- `src/vja/digest/send.py`: `send_email` (one `httpx.post` to Resend, `raise_for_status`, errors →
  `SendError`), `send_digest` orchestrator (build → skip-if-empty → render → pending row → send →
  finalize; `verify`/`config` injectable for offline tests), `load_config` (`.env` via python-dotenv;
  `RESEND_API_KEY`/`resend-api-key`, `VJA_DIGEST_FROM` default sandbox, `VJA_DIGEST_RECIPIENT`), and
  the `vja-digest` console script (`--vertical`, default = all active verticals via new
  `distinct_active_verticals`). Added `python-dotenv` dep.

**Decisions:** D-027 (recipient = env var now → `profiles` at Phase 5), D-028 (empty digest = skip,
no email/row; protects the kill criterion), D-029 (Resend via raw httpx + sandbox sender; pending-row-
before-send lifecycle). Resolved with Hayden: env var bridge (not a new users table — `profiles`
already models a user); sandbox `onboarding@resend.dev`; standalone `vja-digest` (matching slots
between diff and digest at Phase 5, so send stays separate).

**A successful send auto-advances the diff window** — `assembly.last_sent_at` keys the next digest off
`digests.sent_at`, so `mark_sent` needs no extra wiring (pinned by a test).

**Tests:** +18 — `test_digest_render.py` (unit: subject counts, links present, quarantine hidden,
JSON round-trip), `test_digests_repo.py` (lifecycle), `test_digest_send.py` (respx: sent-row+payload,
Resend 4xx & transport-error → failed row, empty → no send/no row, window-advance), and an opt-in
`e2e` real-send (`tests/e2e/`, skipped unless `RESEND_API_KEY`+recipient set — the proof-of-loop test).

**Verified:** ruff + ruff-format + mypy(strict) clean; **108 passed, 4 deselected**; `alembic check`
clean against a fresh migrated DB (no DDL change). Hayden put the Resend key in `.env`. Confirmed end-to-end:
the opt-in `e2e` test sent a real email through Resend.

**Also decided this session (planning, no code):** D-030 — the v1 **dashboard includes recency toggles** (new today /
updated within a week / within two weeks / all open) over the full open set; this is what makes the pull surface worth
opening beside the push digest. Freshness keys on the **ATS posted/updated date** ("posted or updated within the
window"). Surfaced the shared dependency: persisting+normalizing that ATS date is one piece of infra that powers the
Phase-5 backfill cap (D-024), the dashboard toggles (D-030), and apply-speed signals — it rides into Phase 5, toggles
consume it in Phase 6, nothing reorders. Held the 2-week baseline/freshness filter where it is (new users ~2 weeks out).

**Next:** the live proof-of-loop send (needs `VJA_DIGEST_RECIPIENT` = Hayden's Resend account email,
since the sandbox sender only delivers to the account owner), then Phase 4 — the generic Workday
`cxs` fetcher (D-026), the biggest coverage win (~9→24 of 54).

---

## 2026-06-16 — Fix: UTCDateTime type (tz-aware timestamps on every dialect)

**Did:** Replaced the localized `last_sent_at` tz patch (P3B1) with a root-cause fix. Added `UTCDateTime`
(a `TypeDecorator` over `DateTime(timezone=True)`) in `src/vja/db/schema.py` and swapped it onto all 12 timestamp
columns. It normalizes both ends — inbound datetimes → UTC; outbound naive values (SQLite drops tzinfo on read) →
UTC re-attached — so app code never juggles naive-vs-aware datetimes. Removed the now-redundant patch in
`digest/assembly.py`.

**Why:** SQLite returns naive datetimes, Postgres returns aware — same code, different type. Harmless until Python
does datetime math (Phase-5 freshness/age, D-024) or the Postgres cutover, where `naive vs aware` raises/compares
wrong. Fixing at the column type kills the whole class of bug in one place.

**No migration:** underlying DDL is unchanged (`DateTime(timezone=True)`), so `alembic check` reports no drift.

**Tests:** +2 — `test_utc_datetime.py`: a stored timestamp round-trips tz-aware UTC on SQLite; a non-UTC aware input
is normalized to UTC on write.

**Verified:** ruff + mypy(strict) clean; **94 passed, 3 deselected**; `alembic check` clean.

**Next:** Phase 3 · Block 2 — render + Resend send + the `digests` row lifecycle.

---

## 2026-06-16 — Phase 3 · Block 1: digest assembly + verification gate

**Did:** Built the *contents* of the digest + the trust gate in front of it — no sending yet (that's P3B2).
- `src/vja/digest/verification.py`: `verify_apply_url(url, client)` — HEAD (follow redirects) → GET fallback on
  405/501 → pass if final status < 400; any httpx error/timeout = fail (D-008: don't ship a link you can't resolve).
- `src/vja/digest/assembly.py`: `build_digest(engine, vertical, *, now, since, verify) -> DigestContents`
  (`new`/`closed`/`quarantined` lists of `DigestPosting`). Window = `since` last successfully-sent digest
  (`last_sent_at`, normalized to aware UTC); first digest (`since is None`) = baseline (all open → `new`, `closed`
  empty). New postings run the verification gate; dead/missing links → `quarantined`, never shipped. `verify`
  injected (default builds an httpx client) so tests are offline.

**Decisions (this session):** window = since-last-sent-digest (robust to a missed run / failed send); first digest =
baseline of all currently-open. Verification stateless (re-checked each digest; no schema change) — known limitation
logged in the plan (a transient-dead link past the window won't reappear; revisit with a retry flag if it bites).

**Tests:** +12 — `test_verification.py` (respx: HEAD200, HEAD405→GET, redirect, 404, conn-error, 500) and
`test_digest_assembly.py` (baseline; window boundary; auto-resolve `since` from a seeded sent digest; dead-link
quarantine; vertical isolation; `last_sent_at` ignores pending/other-vertical).

**Verified:** ruff + mypy(strict) clean; **92 passed, 3 deselected**. Live e2e: real Camus fetch (3 postings) →
`build_digest` with the **real** verifier → new=3, quarantined=0 (all links resolved live).

**Next:** Phase 3 · Block 2 — render (HTML/text) + Resend send + the `digests` row lifecycle (pending→sent/failed).

---

## 2026-06-16 — Phase 2 · Block 3: orchestration loop + pipeline_runs (Phase 2 complete)

**Did:** Ran `sync_employer` over the whole universe and recorded a run summary — the nightly diff job as one pass.
- `src/vja/db/pipeline_runs.py`: `start_run` (insert `running` + `started_at`) / `finish_run` (finalize status +
  counts + `finished_at`). Written in separate committed transactions so a `running` row is durable before the loop.
- `src/vja/pipeline.py`: `RunSummary` + `run_pipeline(engine, vertical=None, *, now, resolve_fetcher=get_fetcher)`.
  Writes the `running` tombstone → loops `active_fetchable_employers` → per-employer **broad try/except isolation**
  (records `{employer_id,name,error}` in `pipeline_runs.errors`, continues) → finalizes. Status: `ok`/`partial`/
  `failed` (`failed` only if all attempted failed; zero employers = `ok`). `resolve_fetcher` injected for testability.
  Console script **`vja-run`** added (`--vertical`).
- Test fixtures: promoted `migrated_engine`/`alembic_config` to root `tests/conftest.py` (shared by integration +
  the new system tier); fixed the one import.

**Decisions (this session):** running-row-then-finalize (traceable failures — a crash leaves a `running` tombstone);
isolate every employer (one bad employer can't abort the night). Both recorded in the plan; no new D-xxx (they
implement the `docs/04` §7 / `docs/05` health-check / `docs/08` system-tier specs).

**Tests:** +7 — `test_pipeline_runs.py` (running tombstone, finalize) and **system tier** `tests/system/
test_run_pipeline.py` (all-ok; partial on FetchError + run-level no-close guard; partial on *unexpected* exception
isolation; all-failed; idempotent + one run row per run).

**Verified:** ruff + mypy(strict) clean; **80 passed, 3 deselected**. Live e2e: import seed → `vja-run` over the 9
real GH/Lever/Ashby employers → **586 postings persisted, status ok**; re-run → 0 new (idempotent); 2 `pipeline_runs`
rows. The full fetch→diff→persist machine works against real ATS data end-to-end.

**Phase 2 complete.** Next: **Phase 3 — bare digest (proof of loop)**: assemble what changed → verify apply links
(D-008) → email via Resend → schedule. Plan-mode it. (Phase 4 = Workday, per D-026.)

---

## 2026-06-16 — Phase 2 · Block 2: fetch → diff → persist (per-employer) + no-mass-close guard

**Did:** Wired the existing fetchers (Ch 4–5) + `compute_diff` (Ch 6) + `content_hash` (Ch 3) to the DB so one
employer's postings get stored, refreshed, and closed each run. Modular by design: single employer only; the
all-employer loop + `pipeline_runs` summary is Block 3.
- `RawPosting.description` added (last field, default None); each fetcher populates it — Greenhouse `content`,
  Lever `descriptionPlain`→`description`, Ashby `descriptionPlain`→`descriptionHtml` (verified present across all
  fixtures; format may be plain/HTML — fine, the hash compares a posting to its own past).
- `src/vja/fetchers/registry.py`: `get_fetcher(ats_type)` for the 3 Layer-1 ATSs + `SUPPORTED_ATS_TYPES`.
- `src/vja/db/employers.py`: `active_fetchable_employers()` — active GH/Lever/Ashby rows as lean `Employer`s.
- `src/vja/db/postings.py`: repo on a `Connection` — `open_index` (`{external_id: content_hash}`), `insert_posting`,
  `bump_last_seen`, `update_changed`, `close_posting` (never delete — D-009).
- `src/vja/pipeline.py`: `sync_employer(engine, employer, fetcher) -> SyncResult`. Fetch → on `FetchError` return
  `failed` **touching nothing** (THE GUARD) → else `compute_diff` → in one txn: insert new (hash from
  title+location+description), update-or-bump still-present, close vanished.

**Tests:** +11 (registry ×3; Lever description-fallback; `active_fetchable_employers`=9; pipeline ×6 incl. insert/
idempotent/close-not-delete/content-change/hash-includes-description/**the guard: FetchError → 0 closed**). Fetcher
unit tests extended to assert `description`.

**Verified:** ruff+mypy(strict) clean; **73 passed, 3 deselected**. Live e2e: synced real `camusenergy` → 3 postings
persisted with hashes + apply_urls; re-run → 0 new / 3 unchanged (idempotent).

**Docs:** `docs/05` RawPosting contract updated (+`description`). No new DECISIONS (settled-spec implementation).

**Next:** Phase 2 · Block 3 — orchestrate the loop over all active employers (per-employer failure isolation) +
write the `pipeline_runs` run-summary. Plan-mode it.

---

## 2026-06-15 — Phase 2 · Block 1: DB foundation + employer seed import

**Did:** First persistence. Stood up the database so later blocks can store postings + run the diff against state.
Plan-mode decisions this session: **SQLAlchemy Core + Alembic** (D-025), **full 7-table schema now**, **Block 1 =
foundation + employer importer**. Driver: 2 demo users in ~2 weeks → hosting → Postgres soon, so build portable now.
- `src/vja/db/engine.py`: `get_engine` (env URL `VJA_DATABASE_URL`, default local SQLite) + `PRAGMA foreign_keys=ON`
  listener (SQLite ignores FKs otherwise) + `begin()` txn helper.
- `src/vja/db/schema.py`: all 7 `docs/04` tables as Core metadata. Enums = `VARCHAR`+`CHECK` on both dialects
  (`native_enum=False`, keyed to `StrEnum.value`); owned `*_at` = `DateTime(timezone=True)`; `posted_at` stays Text;
  JSON via `sa.JSON`; the spec's uniques/indexes + a posting `CHECK` that exactly one of employer/source is set.
- `src/vja/models.py`: added the remaining schema enums (`Verification` = **verified/detected/layer2**, resolving the
  Chunk-2 drift; `EmployerStatus`/`EmployerSource`/`PostingStatus`/`SourceKind`/`MatchTrigger`/`DigestStatus`/
  `PipelineRunStatus`).
- `migrations/` (Alembic): `env.py` wired to `vja.db` metadata + env URL + SQLite batch mode; autogenerated
  `0001 initial schema`.
- `src/vja/db/employers.py`: idempotent `import_employers_from_csv` (upsert on vertical+name; enum coercion; unknown
  ats_type → UNKNOWN counted; `ImportResult`), `count_employers`, and `main()` → console script `vja-import-employers`.
- `pyproject.toml`: +sqlalchemy/alembic, console script, `migrations/` excluded from ruff+mypy (generated).

**Tests (integration, real SQLite built from the migrations per `docs/08`):** migrations create all 7 tables +
`alembic check` no-drift; FK pragma actually enforced (bad employer_id → IntegrityError); real-seed import (54 rows,
ats distribution matches `docs/07`), known-row spot check, idempotency, verification-enum validity, unknown-ats coercion.

**Verified:** ruff + mypy(strict) clean; **62 passed, 3 deselected**. Manual e2e: `alembic upgrade head` +
`vja-import-employers data/seed/employers_seed.csv` → 54 inserted / 0 unresolved; re-run → 0 inserted / 54 updated.

**Docs:** D-025 (DB stack + Postgres trigger); `docs/04` reconciled (verification enum + SQLAlchemy type notes).

**Next:** Phase 2 · Block 2 — fetch → diff → **persist** postings, with the no-mass-close-on-failure guard as the
headline integration test. Fresh branch.

---

## 2026-06-15 — Chunk 6: diff set arithmetic (last pure-logic piece)

**Did:** Built the daily diff — pure set logic over `external_id`s (`docs/04` lifecycle, D-016/D-009).
- `src/vja/diff.py`: `compute_diff(fetched_ids, stored_open_ids) -> DiffResult(new, still_present, closed)`.
  `new = fetched − stored`, `still_present = fetched ∩ stored`, `closed = stored − fetched`. Accepts any
  iterables (dedups via set semantics); returns `frozenset`s in a frozen `DiffResult`.
- The docstring pins the **no-mass-close guard** as a *caller* responsibility: `compute_diff` can't tell a
  genuinely-empty board from a failed fetch, so the pipeline must skip the diff when a fetch raised `FetchError`.
  (Enforcing that is a Chunk-7+ integration test; here we just compute correctly.)
- `tests/unit/test_diff.py`: 8 units — typical mix, all-new, all-closed (the dangerous empty-fetch case),
  both-empty, no-change, fully-disjoint, iterable/dedup input, and a disjoint-partitions + full-coverage invariant.

**Verified:** default suite **54 passed, 3 deselected**; mypy strict clean; ruff clean (caught a pointless
duplicate set literal `{"b","b"}` → switched to a list to actually test input dedup).

**Milestone:** all pure-logic primitives done (models, content_hash, fetchers ×3, diff). Next chunks introduce I/O
(SQLite) — per the plan, this is where we drop into **plan mode** first to settle DB-access design before coding.

**Next:** Chunk 7 — DB schema + migrations + employer seed-CSV import (the first integration-tested chunk). Will
plan-mode the DB-access approach (raw SQL vs. thin query module vs. SQLAlchemy) before writing. Fresh
`feat/db-schema` branch.

---

## 2026-06-15 — Chunk 5: Lever + Ashby fetchers (Tier-A complete)

**Did:** Added the two remaining clean-JSON fetchers, same pattern as Greenhouse — completing all 9 verified
GH/Lever/Ashby companies.
- `src/vja/fetchers/lever.py`: `LeverFetcher`. Lever returns a bare JSON **array** (no wrapper). Mapping
  (`docs/05`): `external_id = id`, `title = text`, `apply_url = applyUrl or hostedUrl`,
  `location = categories.location`. `createdAt` is epoch-millis (int) → stringified into `updated_at` to keep the
  `RawPosting` type contract. Loud `FetchError` on non-array / no apply link / the usual transport+parse paths.
- `src/vja/fetchers/ashby.py`: `AshbyFetcher`. Returns `{"jobs":[…]}`. Mapping: `external_id = id`,
  `title = title`, `apply_url = applyUrl or jobUrl`, `location = location` (non-string → None),
  `updated_at = publishedAt`.
- Both reuse `build_endpoint` (added in Chunk 4) — no new endpoint code.
- Fixtures: real captures trimmed to 3 jobs each — `tests/fixtures/lever.json` (`voltus`),
  `tests/fixtures/ashby.json` (`weave-grid`) (D-019).
- Tests: 7 Lever + 7 Ashby units via respx (mapping, apply-URL fallback, missing-location → None, empty board,
  shape-mismatch + transport + no-apply-link FetchError paths); 2 opt-in `-m live` smokes.

**Verified:** default suite **46 passed, 3 deselected**; mypy strict clean; ruff clean. Ran `-m live` —
**all 3 fetchers (GH/Lever/Ashby) pass against real endpoints.**

**Next:** Chunk 6 — diff set arithmetic (pure `compute_diff(fetched_ids, stored_open_ids) → new/still_present/closed`,
all empty cases), the last pure-logic piece before DB/persist. Fresh `feat/diff-arithmetic` branch.

---

## 2026-06-15 — Chunk 4: endpoint construction + Greenhouse fetcher (first real fetch)

**Did:** Stood up the first Layer-1 fetcher — the loop now pulls real postings.
- `src/vja/fetchers/endpoints.py`: `build_endpoint(employer)` — derives the URL from `ats_slug` for
  Greenhouse/Lever/Ashby; uses the explicit `endpoint` column for Workday/others; raises `ValueError`
  (a *config* defect, distinct from a runtime `FetchError`) when neither is possible.
- `src/vja/fetchers/greenhouse.py`: `GreenhouseFetcher` (satisfies the `Fetcher` Protocol). GET
  `…/boards/{slug}/jobs?content=true`, maps each job per `docs/05` (`external_id = str(id)` — D-016 string
  key; `title`; `apply_url = absolute_url`; `location = location.name`; `updated_at`; full job → `raw`).
  Every failure mode is loud: non-200, network error, non-JSON, missing `jobs` list, non-object job, and
  missing required field all raise `FetchError` — never a silent empty/garbage result. Injectable httpx
  client; identifiable User-Agent (politeness, `docs/05`).
- `tests/fixtures/greenhouse.json`: captured real `camusenergy` response (3 jobs, full structure — D-019 golden).
- Tests: 6 endpoint-construction units (each ATS + the two raise paths); 9 Greenhouse units via respx against the
  fixture (mapping, int→str id, missing location → None, empty board → `[]`, + 5 FetchError paths); 1 opt-in
  `-m live` smoke that pins Greenhouse's *response shape* (catches ATS drift), in new `tests/live/`.

**Verified:** default suite **32 passed, 1 deselected**; mypy strict clean; ruff clean. Ran `-m live` once —
real fetch against camusenergy **passed** (first proof the fetch path works end-to-end).

**Note:** wiring `content_hash` (Chunk 3) to the Greenhouse description (`content`) happens at persist time, not in
the fetcher — comes with the diff/persist chunk.

**Next:** Chunk 5 — Lever + Ashby fetchers (same pattern, fixtures from `voltus` / `weave-grid`), completing the 9
verified GH/Lever/Ashby companies. Fresh `feat/lever-ashby-fetchers` branch.

---

## 2026-06-15 — Chunk 3: content_hash canonicalization

**Did:** Built the extraction cache's correctness primitive (`docs/04` §3).
- `src/vja/hashing.py`: `content_hash(*, title, location, description) -> str` — hex SHA-256 over a canonical,
  sorted-key JSON object of the **stable fields only**. `_normalize` collapses whitespace runs + strips (so reflowed
  HTML / trailing newlines don't churn the hash) while keeping case. Volatile junk (view counts, "updated X ago",
  tracking params, request timestamps) is excluded *by construction* — it's never passed in.
- `tests/unit/test_hashing.py`: 9 unit tests — determinism + 64-char hex shape; a **golden-value regression lock** on
  the canonical form (so any normalization change is a deliberate, reviewed decision rather than a silent cache-wide
  invalidation); whitespace-invariance; None≡empty; sensitivity to each of title/location/description; case-significance;
  and a volatile-payload-exclusion test documenting intended caller usage.

**Note:** `content_hash` is the pure function only. Wiring it to each ATS's description field (Greenhouse `content`,
Lever/Ashby `descriptionPlain`) lives in the fetcher/persist chunks — `RawPosting` carries the description inside
`raw`, so extraction of the stable description is per-ATS and comes later.

**Gates:** ruff format/check, mypy (strict), pytest (**17 passed**) all green.

**Next:** Chunk 4 — endpoint construction + the Greenhouse fetcher + a captured fixture (`tests/fixtures/greenhouse.json`)
+ mapping unit test + opt-in `-m live` smoke. On a fresh `feat/greenhouse-fetcher` branch.

---

## 2026-06-15 — Chunk 2: domain models + Fetcher contract

**Did:** Froze the contract everything builds on (`docs/04`/`05`).
- `src/vja/models.py`: `RawPosting` and `Employer` as frozen, slotted dataclasses (value objects — a fetcher is a
  pure read and never mutates them); schema enums `AtsType`, `Level`, `RemoteType`, `Verdict` as `StrEnum` so a
  member's `.value` is exactly the string the DB stores. `RawPosting.external_id` documented as THE diff key (D-016),
  never synthesized from the title.
- `src/vja/fetchers/base.py`: the `Fetcher` `Protocol` (`runtime_checkable`) + `FetchError`, whose docstring pins the
  highest-stakes rule — a raised `FetchError` must never be read as "zero open jobs" (no mass-close on failure).
- `tests/unit/test_models.py`: 7 unit tests — field mapping, `None`-optionals, immutability (frozen raises), enum
  `.value` strings + value→member round-trip (used by the later seed import), Protocol conformance, `FetchError` type.

**Spec reconciliation:** `docs/04` §1's `ats_type` list was narrower than the seed CSV (missing `icims`, `radancy`,
`custom`, etc.). Modeled `AtsType` as the full superset (grouped by build tier per `docs/07`) and updated `docs/04`
to match, naming `vja.models.AtsType` as the enum source of truth. **Open:** the `verification` enum has the same
drift (`docs/04` says verified/suspect/unverified; seed uses verified/detected/layer2) — defer to the DB-import chunk
where it's consumed.

**Gates:** ruff format/check, mypy (strict), pytest (8 passed) all green.

**Next:** Chunk 3 — `content_hash` canonicalization (pure fn + hard unit tests: invariant under volatile junk + key
order; changes with description). On a fresh `feat/content-hash` branch.

---

## 2026-06-15 — Chunk 1b: CI workflow + pre-commit (gates machine-enforced)

**Did:** Made the D-021 gate suite enforceable, not just locally runnable. Bundled with Chunk 1 as one
"project setup" change (CI has nothing to gate until the scaffold exists).
- `.github/workflows/ci.yml`: two jobs on `pull_request` + push-to-`main` — `gates` (`uv lock --check` →
  `uv sync --locked` → ruff format/check → mypy → pytest) and `secrets` (gitleaks, full-history). Pinned actions
  (`checkout@v4`, `astral-sh/setup-uv@v5` w/ cache, `gitleaks-action@v2`); `concurrency` cancels superseded runs.
- `.pre-commit-config.yaml`: local-repo hooks that shell out to `uv run` (single source of truth for tool versions)
  — ruff format, ruff check, mypy, pytest. Mirrors CI (`docs/09` "same checks, two moments").
- Added `pre-commit` to the dev group; re-locked.

**Deferred on purpose:** the path-filtered `eval` gate (D-020/D-021) — no prompt/matching code exists to evaluate
yet; it lands with the Week-3 matching engine, the change it actually guards.

**Gates:** `uv lock --check`, ruff format/check, mypy (strict), pytest all green; `pre-commit run --all-files`
passes all four hooks; both YAML files parse. CI's own proof is the first PR running green on GitHub.

**Next:** push this branch → open the "project setup" PR (scaffold + CI) → confirm CI green. Then resume
branch-per-chunk with **Chunk 2** (domain models + Fetcher contract) on a fresh `feat/domain-models`.

---

## 2026-06-15 — Chunk 1: uv scaffold + tooling (first code)

**Did:** Stood up the Python project. Code starts here.
- Installed `uv` (0.11.21) via the standalone installer — Homebrew couldn't resolve `formulae.brew.sh` in this env; the standalone installer worked. uv lives at `~/.local/bin` (D-014).
- `pyproject.toml`: package `vja` (src layout, hatchling build), runtime dep `httpx`; dev group `pytest`/`ruff`/`mypy`/`respx`/`freezegun`. Ruff (E,F,I,UP,B,SIM, line-length 100), `mypy --strict`, pytest config with the opt-in markers `live`/`e2e`/`eval` excluded from the default run (D-020/`docs/08`).
- `src/vja/__init__.py` (carries the D-004 "no vertical-specific code" rule as a module docstring), `tests/unit/test_scaffold.py` smoke test, `uv.lock` committed.

**Gates:** `ruff format --check`, `ruff check`, `mypy` (strict), `pytest` all green off a clean tree.

**Decisions:** none re-litigable; import package named `vja` (Hayden-approved). No DECISIONS entry needed.

**Next:** Chunk 2 — freeze the domain models + Fetcher contract (`models.py`: `RawPosting`/`Employer`/enums per `docs/05`; `fetchers/base.py`: `Fetcher` Protocol + `FetchError`), with a `RawPosting` immutability unit test. Pause for diff review before Chunk 3.

---

## 2026-06-11 (end of day) — corrected vertical order + logged two-stage filter

**Did:** Two small but real corrections before code starts.
- **Energy is the first-built vertical, not aviation (D-022).** The repo was quietly contradicting itself — CLAUDE.md's
  build sequence said "weeks 1–2 aviation / week-4 energy" while the seed data is grid/power and `docs/06` already
  treated *aviation* as the week-4 add. Hayden confirmed energy-first. Fixed CLAUDE.md (build sequence + verticals
  intro), the stray "week-4 energy" references in `docs/08`/`docs/09`, and the D-002 why-line.
- **Logged the two-stage cheap filter (D-023).** Hayden flagged that the LLM resume-match should sit on top of a
  cheaper, free filtering layer. Captured the shape: **Stage A** = free scope/relevance gate on the L1 title
  (in-scope role/geo/level at all) *before any LLM extraction*; **Stage B** = the existing cheap level/location/
  work-auth pre-filter → `matches.score`; only Stage-B survivors reach the strong rationale model. The concept was
  already implied (CLAUDE.md pre-filter, `04.score`, `08` unit test) but the *free title-level Stage A* wasn't
  specified. Full mechanics deferred to the week-3 matching spec. Updated CLAUDE.md execution model to match.

**Readiness check:** confirmed nothing blocks code. The Greenhouse fetcher's inputs are fully specced (`05` contract +
endpoint, `04` schema + diff lifecycle, D-019 fixtures). Open: aviation seed (week-4), and the eval/matching specs
(week-3) — neither blocks week-1.

**Next session:** start building. Scaffold the uv project → freeze `Fetcher`/`RawPosting` from `docs/05` → capture one
real Greenhouse response into `tests/fixtures/` → write the mapping + its unit test. First fetch runs over the verified
**grid/power** Greenhouse slugs (`amperon`, `camusenergy`, `janestreet`, `yesenergy`).

---

## 2026-06-11 (later still) — testing strategy + dev workflow docs

**Context:** Hayden verified most seed links (a few problematic ones to filter later) and flagged that since
~all code here is Claude-written, testing must be rigorous. Asked for testing docs (unit→integration→system→e2e),
a when-to-use protocol, and any other standard dev protocols worth adopting.

**Wrote:**
- `docs/08-testing-strategy.md` — the four levels in this project's own terms (fetcher mapping + `content_hash`
  + diff arithmetic as units; fetch→diff→persist, the **no-mass-close-on-failure** guard, extraction-cache reuse,
  `matches` versioning as integration; whole-pipeline run + idempotency + verification gate as system; live ATS
  smoke + full real send as opt-in e2e). Plus a dedicated **LLM-as-evals** section (mock the SDK in L1–3; pin model
  behavior with property assertions + an "obvious no" case, graded with tolerance, metered) and a when-to-write
  table. Builds on D-019, doesn't contradict it.
- `docs/09-dev-workflow.md` — Definition of Done, branch/small-PR flow, the human-read-the-diff review gate,
  CI+pre-commit gates (ruff/mypy/pytest/secret-scan/uv-lock), config-not-code as a checkable rule, and an explicit
  "what we deliberately skip for now" list.

**Decisions:** D-020 (four-level taxonomy; fast/offline default suite; regression-test-first; LLM evals as a
**path-filtered merge gate** — structural props block hard, behavioral "obvious-no" cases gate on a threshold, and
the whole eval job only runs in CI when a PR touches prompt/matching/extraction code), D-021 (DoD + automated gates +
mandatory human diff review; **mypy** chosen over pyright). Updated CLAUDE.md doc map + a testing/DoD policy bullet.

**Hayden's calls this session:** fine with evals as a real merge gate (token cost ≈ one normal query, worth it to
catch a prompt regression before it ships in a digest); picked mypy. Design answer to the flake worry = path-filter
the gate + threshold/majority on behavioral cases, not weaken it.

**Next:** unchanged from prior session — scaffold the uv project and freeze the `Fetcher` interface; first real tests
land with the GH/Lever/Ashby fetchers (unit mapping tests against captured fixtures = the first thing built under D-020).

---

## 2026-06-11 (later) — ATS-identification pass

**Did:** Classified all 54 grid/power employers by ATS platform (live endpoint probes → careers-page signature
detection → web-search reading ATS domains from result URLs → live endpoint verification incl. the Workday `cxs` API).

**Result — 22 verified / 16 detected / 16 layer2:**
- **Workday is dominant (15).** The generic `cxs` POST API is **live-verified** for 12 (AES 111, Vistra 193, S&P 234,
  Shell 174, Duke 96, Xcel 123, CME 69, Trafigura 97, Wood Mac 68, Macquarie 25, PJM 13, Stem 12). One generic fetcher.
- **Greenhouse 5** (incl. DRW slug `drweng`=147), **Lever 3** (Kraken/Octopus slug `octoenergy`=162, corrects earlier suspect),
  **Ashby 1** — all verified.
- **Tier B:** iCIMS 4, Workable 2 (Energy Aspects API valid), Oracle HCM 2, SmartRecruiters 1.
- **Tier C singletons:** Jobvite, SuccessFactors, Avature, UKG, Eightfold (1 each).
- **Layer 2 (16):** 3 Radancy/Phenom enterprise portals + 13 custom sites.
- **Deterministic ceiling ≈ 70%** via ~8 platform fetchers; ~30% → Layer 2. Vindicates "no per-company scrapers."

**Wrote:** `docs/07-ats-routing.md` (distribution + build priority); rewrote `employers_seed.csv` with full
classification (Workday endpoints encoded as `tenant:dc:site` + full cxs URL); updated seed README, CLAUDE.md doc map,
and DECISIONS (D-017 no-custom-scrapers, D-018 build order, D-019 fixture-based tests).

**Open fixups:** GE Vernova / BP Workday site-path; Castleton tenant prefix; Vortexa Workable slug; double-check
Fluence/Enverus/Aurora before defaulting them to Layer 2.

**Next:** scaffold uv project, freeze the `Fetcher` interface, build GH/Lever/Ashby with captured fixtures.

---

## 2026-06-11 — Planning kickoff + grid/power seed data

**Decided (see DECISIONS.md for the durable record):**
- Pipeline runtime: **local machine** (cron/launchd) for week 1; documented path to a small VPS later.
- Transactional email: **Resend**.
- Python toolchain: **uv**.
- Seed-data split: Hayden curates company names + priority columns; Claude resolves ATS by probing live endpoints.

**Did:**
- Read all four planning docs (CLAUDE.md + docs/01–03). Confirmed the spec is settled; this phase is build-prep, not re-planning.
- Created `data/seed/` with `employers_seed.csv` + a column/workflow `README.md`.
- Ingested Hayden's 54-company **grid/power** list (from `data1.xlsx`), preserving his curation columns (tier, category, key_cities, role_tilt).
- Resolved ATS by probing live Greenhouse/Lever/Ashby JSON endpoints:
  - **7 verified** (live, jobs > 0): Amperon, Arcadia, Camus Energy, Jane Street, Voltus, Yes Energy, WeaveGrid.
  - **3 suspect** (slug resolved but board looks wrong): Constellation Energy, Koch Industries, Kraken (Octopus).
  - **44 unverified** (Workday/custom best-guesses): utilities, banks, quant funds, exchanges, a few startups.
- Added build-spec docs: `04-data-model-spec.md`, `05-fetcher-interface-spec.md`, `06-vertical-config-spec.md`; started `DECISIONS.md`; appended a documentation-discipline section to CLAUDE.md.
- Prepped repo for GitHub: `git init` (branch `main`) at the project root (`vertical-job-agent-starter/`), added `.gitignore` (Python/uv/env/db/OS) and a root `README.md`. Not committed — Hayden does add/commit/push.
- Reasoned through the custom/Workday scraper question: conclusion is *don't write N per-company scrapers* — bucket the 47 into Workday (one generic fetcher + per-tenant config), other known ATSs (a few generic fetchers), and a small truly-bespoke tail (default to Layer 2 LLM-read). Next step proposed: an ATS-identification pass to get the real distribution.

**Open threads / next:**
- Aviation vertical not yet seeded.
- The 44 unverified + 3 suspect rows need ATS confirmation (web research or just let the Layer 1 fetcher 404-test the guesses).
- Net code written so far: none. Next build step = Layer 1 skeleton (repo scaffold with uv, employers table, Greenhouse/Lever/Ashby fetchers, postings table, diff job, bare email).
