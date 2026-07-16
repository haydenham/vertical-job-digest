# Phase 9.5 — Cloud Deploy: Plan of Record

*Working execution plan for Phase 9.5 (cloud deploy + Postgres cutover + go-live). Lives in the repo
because chats reset between blocks — a fresh session should read this + `docs/11` (the ledger) + the
WORKLOG top entry and be able to continue. This is a **plan**, not an invariant source: when a block lands,
its decisions go to `DECISIONS.md`, the live rules to `docs/INVARIANTS.md`, and the ledger checkboxes in
`docs/11` get ticked. Authority order unchanged (build specs > CLAUDE.md > memos); this doc is a memo-tier
working plan.*

**Status:** **9.5a ✅** (D-059, merged to `main` via PR #45 @ `fd347cd`). **9.5b ✅** (D-060, merged to
`main` via PR #46 @ `0abbb5b`). **9.5c ✅** (D-061 — GCP project `role-feed-prod`, Neon, Secret Manager,
Artifact Registry, OAuth, Resend all provisioned; runbook `deploy/gcp/README.md`; merged to `main` via PR #47
@ `74644e1`). **9.5d ✅ (go-live infra done, D-067)** — deployed to Cloud Run + Neon, `role-feed.com` live, auth
guards flipped ON (`VJA_AUTH_REQUIRED=1`); the mid-cutover `VJA_VERTICALS_DIR` bug was fixed (D-063, PR #49). The
executable runbook is **`deploy/gcp/CUTOVER.md`**. **Closeout still open:** real email E2E + `/security-review`.
**Blocker before beta users:** the onboarding/dashboard flow is broken (one-vertical-per-user routing, D-064/065)
— the fix is the plan of record in **`docs/13-onboarding-and-shipping-plan.md`** (Phase A ship-script → Phase B
overhaul). §9.5d below is the cutover index.

---

## Locked decisions (run through Hayden 2026-06-29)

| Decision | Choice | Why |
|---|---|---|
| **Compute** | GCP **Cloud Run** (service for API+SPA; **Cloud Run Job** + Cloud Scheduler for nightly) | the 9.1 lean; D-031 trigger-swap; stdout logs already fit |
| **Postgres host** | **Neon** (serverless, free tier), *not* Cloud SQL | honors D-025 "cutover = a URL swap"; ~$0 at demo scale; no GCP coupling; Neon→Cloud SQL later is the same URL swap if ever needed |
| **Domain** | buy a **`.com`** via **Cloudflare Registrar** (~$10/yr) | required for Resend verified sending domain (deliverable email) + stable OAuth redirect + cookie domain; `.com` for inbox reputation |
| **Data migration** | **Fresh Postgres, no carryover** + a **suppressed baseline run** | sqlite→PG migration is throwaway risk; `vja.db` is disposable-by-design; postings re-fetch nightly; the 425 matches / 3 profiles are test data. Baseline run stamps `first_seen_at` so the first real digest is a normal delta, not a monster |
| **Sequencing** | **Four sub-blocks** (9.5a–d); a/b are code-now, c/d are ops-later | each PR-sized with a real gate; code progress isn't blocked on provisioning |

**Secrets needed in prod** (all env, → Secret Manager at 9.5c): `ANTHROPIC_API_KEY`, `RESEND_API_KEY`,
`VJA_DATABASE_URL` (Neon), `VJA_SESSION_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`VJA_DIGEST_FROM` (verified domain), `VJA_DIGEST_RECIPIENT` (ops/alert addr), `VJA_AUTH_REQUIRED=1`,
`VJA_CORS_ORIGINS` (if SPA ever off-origin; same-origin needs none), `VJA_PUBLIC_BASE_URL` (see 9.5a-2).

**Layer-2 routing (D-090):** embedded LiteLLM currently defaults to
`VJA_EXTRACT_MODEL=anthropic/claude-haiku-4-5` and
`VJA_MATCH_MODEL=anthropic/claude-sonnet-4-6`, so Block 1 needs no production env/secret mutation. A later
provider cutover must add its credential to Secret Manager + both complete `ship.sh` secret lists and set the
model route as a preserved non-secret Cloud Run variable; the evaluated Anthropic route remains rollback.

---

## Block map

| Block | Theme | Code? | Gate | Status |
|---|---|---|---|---|
| **9.5a** | App hardening (cookies, proxy/HTTPS redirect, SPA catch-all, bind, CORS) | yes (Python) | pytest + full gate | ✅ D-059 |
| **9.5b** | Containerization (multi-stage Dockerfile, `.dockerignore`, local prod-parity smoke) | yes (infra) | `docker build` + run | ✅ D-060 |
| **9.5c** | Provision (GCP project, Neon, domain→Cloudflare DNS, Secret Manager, Artifact Registry) | no (docs + manual) | docs in `deploy/gcp/` | ✅ D-061 |
| **9.5d** | Cutover & go-live (deploy, `alembic upgrade`, baseline run, email verify, flips, security review) | no app code | `/security-review` + smoke | ☐ |

9.5a and 9.5b can be built and merged **before any GCP/Neon/domain exists**.

---

## 9.5a — App hardening (detailed)

All changes are in `src/vja/api/` and are unit-testable offline. Goal: the app behaves correctly behind a
TLS-terminating proxy with auth enforced, *without* breaking the local dev experience (http localhost, no
proxy). Every prod behavior is **env-gated** so dev defaults are unchanged.

### 9.5a-1 — Session cookie hardening
- **Where:** `create_app` in `api/app.py` (the `SessionMiddleware` add, currently `secret_key` only).
- **Do:** extract a pure helper `session_cookie_kwargs() -> dict` (in `api/auth.py`, next to
  `session_secret`) returning `secret_key`, `same_site="lax"` (must stay `lax` — OAuth's top-level GET
  redirect from Google breaks under `strict`), `https_only=<env>`, `max_age=<env>`. Drive `https_only`
  from a single prod flag — reuse/derive from a new `VJA_COOKIE_SECURE` (default off so dev http works;
  set `1` in prod). `max_age` from `VJA_SESSION_MAX_AGE` (default 14 days).
- **Test:** `session_cookie_kwargs` returns `https_only=False` by default, `True` when env set; `same_site`
  is always `lax`. (Pure function → trivial unit test, no middleware introspection.)

### 9.5a-2 — HTTPS redirect_uri behind the proxy *(the OAuth go-live blocker)*
- **Problem:** `login()` builds the OAuth redirect via `request.url_for("auth_callback")`. Behind Cloud
  Run's TLS terminator the internal scheme is `http`, so this yields `http://…/auth/callback`, which
  **won't match** the `https://` URI registered with Google → `redirect_uri_mismatch`.
- **Do (primary, explicit):** when `VJA_PUBLIC_BASE_URL` is set, build `redirect_uri = f"{base}/auth/callback"`
  instead of `request.url_for`. Removes all proxy/scheme ambiguity; the prod URL is known config.
- **Do (belt-and-suspenders):** in `api_main`, pass `proxy_headers=True, forwarded_allow_ips="*"` to
  `uvicorn.run` so `X-Forwarded-Proto: https` is honored even where url_for is used.
- **Test:** with `VJA_PUBLIC_BASE_URL` set, `login` calls `authorize_redirect` with the https base URI
  (mock `oauth.google.authorize_redirect`, assert the redirect_uri arg); unset → falls back to `url_for`.

### 9.5a-3 — SPA deep-link catch-all
- **Problem:** `StaticFiles(directory=dist, html=True)` mounted at `/` serves `index.html` for `/` but
  **404s a hard refresh of `/upload` or `/login`** (no such file). Client-side nav works; deep links don't.
- **Do:** when `dist` exists, mount real assets (`app.mount("/assets", StaticFiles(directory=dist/"assets"))`)
  and add a trailing catch-all `@app.get("/{full_path:path}")` that returns `FileResponse(dist/full_path)`
  when that path is an existing file (favicon, etc.), else `FileResponse(dist/"index.html")`. Declared
  **last** so all `/api/*` and `/auth/*` routes win; the catch-all only handles SPA routes + static files.
- **Test:** with a fake `dist` (tmp `index.html` + an asset), `GET /upload` → 200 returning index.html;
  `GET /api/health` still 200 JSON; an existing static file is served verbatim. Guard the no-dist case
  (dev/CI without a build) — catch-all is only registered when `dist.is_dir()`.

### 9.5a-4 — Container bind (`0.0.0.0:$PORT`)
- **Problem:** `api_main` defaults `--host 127.0.0.1`; Cloud Run injects `$PORT` (default 8080) and requires
  binding `0.0.0.0`.
- **Do:** default `--port` from `int(os.environ.get("PORT", "8000"))` and `--host` from
  `os.environ.get("VJA_API_HOST", "127.0.0.1")`. Local dev unchanged (127.0.0.1:8000); the container's CMD
  passes `--host 0.0.0.0` (or sets `VJA_API_HOST`), and Cloud Run's `PORT` is honored automatically.
- **Test:** refactor arg parsing into a `_parse_args(argv)` so a unit test can assert `PORT`/`VJA_API_HOST`
  env feed the defaults (without invoking `uvicorn.run`).

### 9.5a-5 — Prod CORS (mostly confirm)
- `_cors_origins()` is already env-driven (`VJA_CORS_ORIGINS`). Prod is same-origin (SPA served by FastAPI)
  → CORS unused. No code change expected; just document that off-origin frontends set `VJA_CORS_ORIGINS`
  (cannot be `*` with `allow_credentials=True`, which we rely on). Add a note, no behavior change.

### 9.5a DoD
Full Python gate green (ruff format/check, mypy, import-linter, `uv lock --check`, pytest on SQLite +
Postgres), new unit tests for each seam above, human-read diff, docs updated (ADR for 9.5a + INVARIANTS
auth/dashboard lines noting cookie-hardening/redirect/catch-all are live; tick docs/11 §3.2 sub-items).
**STOP for Hayden to commit + PR.**

---

## 9.5b — Containerization ✅ (D-060, as built)

- **Multi-stage `Dockerfile`** at repo root: stage `web` (`node:24-bookworm-slim` — **Debian/glibc, not
  alpine**, to avoid the musl Rollup optional-binary break) `npm ci && npm run build` → `frontend/dist`;
  runtime stage (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`) does a **non-editable** `uv sync` (deps
  layer then project layer), copies the built `dist` in, `CMD vja-api --host 0.0.0.0`. SPA served same-origin
  via the 9.5a catch-all; honors `$PORT`.
- **`VJA_FRONTEND_DIST`** (new `app.frontend_dist_dir()` helper) makes the dist dir explicit config — the
  non-editable install moves the package off the repo layout the old `parents[3]/frontend/dist` assumed; set
  to `/app/frontend/dist` in the image, defaults to repo layout for dev/CI.
- **`.dockerignore`** excludes `.venv`, `node_modules`, the host `frontend/dist` (rebuilt in-image),
  `data/*.db`, `.git`, caches, `tests`/`docs`/`deploy`, local `.env`.
- **Runtime data baked in:** `config/`, `migrations/` + `alembic.ini`, `data/seed/` (alembic upgrade at 9.5d;
  nightly/import). **No secrets / `VJA_DATABASE_URL` in the image** — all runtime env.
- **One image, two run targets** (D-031): default `vja-api` (Cloud Run service); the Cloud Run **Job**
  overrides the entrypoint to `vja-nightly` — no second build.
- **Local prod-parity smoke** (run from repo root):
  ```sh
  docker build -t rolefeed:smoke .
  docker run --rm -p 8000:8000 rolefeed:smoke
  curl -s localhost:8000/api/health            # {"status":"ok"}
  curl -s localhost:8000/ ; curl -s localhost:8000/upload   # the Rolefeed SPA (catch-all)
  ```
  Verified: health ok, `/` + `/upload` return the SPA, `/assets/*` 200, unknown `/api` 404, binds
  `0.0.0.0:8000`, both entrypoints present (601 MB image).

## 9.5c — Provision ✅ (D-061, as built — runbook: `deploy/gcp/README.md`)

Manual + the written runbook (`deploy/gcp/README.md`), no app code. As executed (2026-06-30):
1. **Domain:** `role-feed.com` (Cloudflare Registrar — **hyphenated**, vs the `<rolefeed>.com` this sketch
   assumed). DNS stays on Cloudflare.
2. **Neon:** project/DB in **AWS us-east-2 (Ohio)**; `VJA_DATABASE_URL` stored as the **pooled** endpoint
   with the `postgresql+psycopg://` scheme (the dashboard hands out bare `postgresql://` — the `+psycopg`
   rewrite is mandatory). Local connect blocked by laptop-network port-5432 filtering → authoritative
   connect/migration deferred to 9.5d via Cloud Run Job exec.
3. **GCP project** `role-feed-prod` (#850723734041) + billing. APIs enabled: Cloud Run, Artifact Registry,
   Cloud Scheduler, Secret Manager. (No Cloud SQL — Neon.)
4. **OAuth:** web client **in `role-feed-prod`** (consent screen External/Testing + test users); redirect
   `https://role-feed.com/auth/callback`. The `*.run.app` fallback URI is added at 9.5d once the service URL
   exists.
5. **Secret Manager:** all 8 secrets loaded (the table above).
6. **Artifact Registry:** Docker repo `rolefeed` in `us-central1`.
7. **Resend:** `role-feed.com` verified (SPF/DKIM in Cloudflare); `VJA_DIGEST_FROM=digest@role-feed.com`.

## 9.5d — Cutover & go-live (index → `deploy/gcp/CUTOVER.md`)

The executable, safety-ordered runbook lives in **`deploy/gcp/CUTOVER.md`** (the 9.5d analogue of the 9.5c
`deploy/gcp/README.md`). Ordering principle: `artifact → schema → seed → deploy(auth OFF) → smoke → domain →
auth ON`. The steps, in brief:

1. Build (`--platform linux/amd64` — arm64 laptop gotcha) + push the image to Artifact Registry.
2. Grant the Cloud Run runtime SA `secretmanager.secretAccessor`.
3. `alembic upgrade head` against Neon — **run locally** (Hayden's laptop reaches Neon; the earlier "Cloud
   Run Job exec" assumption is obsolete). Baseline seed (`vja-import-employers` → `vja-run` (no LLM/no send,
   stamps `first_seen_at`) → `vja-load-profiles`) also runs locally.
4. Deploy the **Cloud Run service** with secrets mounted, **auth OFF**; **staged smoke on the `*.run.app`
   URL** (health, SPA deep-link, a real login round-trip) before touching domain/auth.
5. Map the **custom domain**; deploy the **Cloud Run Job** (`vja-nightly`) + **Cloud Scheduler** trigger.
6. **Flip the prod guards last:** `VJA_AUTH_REQUIRED=1`, `VJA_COOKIE_SECURE=1`, `VJA_PUBLIC_BASE_URL`; confirm
   anon `/api/postings` → 401 + login on the real domain. Real test send. Rollback = `update-traffic`.
7. **`/security-review`** on the cutover diff, then docs (docs/11 §3, DECISIONS cutover ADR, INVARIANTS
   auth-required ON, CLAUDE.md 9.5 ✅).

**Deferred past 9.5d (note, don't silently forget):** deletion/data-subject endpoint (docs/11 §3.1),
per-IP/edge rate-limiting + captcha (§3.3 — OAuth bounds abuse meanwhile), spend-trend observability/alerting
(§3.5), Neon PITR retention confirm. **Post-launch deploy loop** (data-only vs config/code redeploy; the
merge-triggered "9.6" auto-deploy) is documented in `docs/11` §5.

---

## For the next chat (post-reset)
Read `docs/INVARIANTS.md` → WORKLOG top → **this file**. Find the next ☐ block above; its detail (9.5a) or
sketch (9.5b–d, refine before building) is the spec. Locked decisions are fixed unless Hayden reopens them.
