# Phase 9.5 — Cloud Deploy: Plan of Record

*Working execution plan for Phase 9.5 (cloud deploy + Postgres cutover + go-live). Lives in the repo
because chats reset between blocks — a fresh session should read this + `docs/11` (the ledger) + the
WORKLOG top entry and be able to continue. This is a **plan**, not an invariant source: when a block lands,
its decisions go to `DECISIONS.md`, the live rules to `docs/INVARIANTS.md`, and the ledger checkboxes in
`docs/11` get ticked. Authority order unchanged (build specs > CLAUDE.md > memos); this doc is a memo-tier
working plan.*

**Status:** planning complete; 9.5a not started. Branch: `feat/cloud-deploy` (off `main` @ `250aa38`).

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

---

## Block map

| Block | Theme | Code? | Gate | Status |
|---|---|---|---|---|
| **9.5a** | App hardening (cookies, proxy/HTTPS redirect, SPA catch-all, bind, CORS) | yes (Python) | pytest + full gate | ☐ |
| **9.5b** | Containerization (multi-stage Dockerfile, `.dockerignore`, local prod-parity smoke) | yes (infra) | `docker build` + run | ☐ |
| **9.5c** | Provision (GCP project, Neon, domain→Cloudflare DNS, Secret Manager, Artifact Registry) | no (docs + manual) | docs in `deploy/gcp/` | ☐ |
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

## 9.5b — Containerization (sketch — refine when reached)

- **Multi-stage Dockerfile** at repo root: stage 1 (node) `cd frontend && npm ci && npm run build` →
  `frontend/dist`; stage 2 (python, `uv`) install the package, copy `dist` in, `CMD vja-api --host 0.0.0.0`.
  The SPA is served same-origin by FastAPI (the 9.5a catch-all). Honors `$PORT`.
- **`.dockerignore`** (exclude `.venv`, `node_modules`, `data/*.db`, `.git`, caches, `frontend/dist`
  rebuilt in-image).
- **The nightly** ships in the *same image* (it has `vja-nightly`); the Cloud Run **Job** just overrides the
  entrypoint to `vja-nightly`. One image, two run targets — no second build.
- **Local prod-parity smoke:** `docker build` then run with a SQLite volume + a built SPA, hit `/api/health`,
  `/`, `/upload` (catch-all), confirm the SPA loads. Document the command.
- **Gate:** image builds; local smoke passes. DoD + STOP to commit + PR.

## 9.5c — Provision (sketch — Hayden-led, documented in `deploy/gcp/`)

Manual + a written runbook (`deploy/gcp/README.md`), no app code. Order:
1. **Domain:** buy `<rolefeed>.com` (Cloudflare Registrar). DNS stays on Cloudflare.
2. **Neon:** create project/DB; grab the `postgresql+psycopg://…` URL (note: SQLAlchemy needs the
   `+psycopg` driver prefix, already a dep from 9.1).
3. **GCP project** (`rolefeed-prod`) + billing. Enable: Cloud Run, Artifact Registry, Cloud Scheduler,
   Secret Manager. (No Cloud SQL — Neon.)
4. **OAuth:** consent screen External / **Testing** mode (add Hayden + demo users as test users → skips
   Google verification). Create Web credentials; redirect URI = `https://<domain>/auth/callback` (and the
   `*.run.app` URL as a fallback). Defer until the public URL/domain is known.
5. **Secret Manager:** load every secret from the table above.
6. **Artifact Registry:** a Docker repo for the image.
7. **Resend:** add `<domain>` as a sending domain; paste SPF/DKIM into Cloudflare DNS; set
   `VJA_DIGEST_FROM=digest@<domain>` (or similar). (Verification is async — start early.)

## 9.5d — Cutover & go-live (sketch)

1. Build + push the 9.5b image to Artifact Registry.
2. Deploy the **Cloud Run service** (API+SPA) with secrets mounted; map the **custom domain**.
3. Set the OAuth redirect URI to the final `https://<domain>/auth/callback`; set `VJA_PUBLIC_BASE_URL`.
4. **Neon schema:** `alembic upgrade head` against the Neon URL (one-off, from a local shell or a Cloud Run
   Job exec).
5. **Baseline run (digest suppressed):** `vja-import-employers` → one `vja-run` (fetch→diff→persist, **no
   send**) to stamp `first_seen_at` across the universe. Then load Hayden's profile (via the upload UI or
   `vja-load-profiles`).
6. Deploy the **Cloud Run Job** (`vja-nightly`) + **Cloud Scheduler** trigger (the D-031 swap). First
   scheduled run sends the first *real* (normal-delta) digest.
7. **Email:** confirm Resend domain verified; send a test digest to a real external address.
8. **Flip the prod guards:** `VJA_AUTH_REQUIRED=1`, `VJA_COOKIE_SECURE=1`. Confirm anonymous `/api/postings`
   → 401, login round-trips end-to-end on the real domain.
9. **`/security-review`** on the full cutover diff (the docs/11 §3.1 gate) before announcing.
10. Update docs/11 (§3 checkboxes), DECISIONS (the cutover ADR), INVARIANTS (auth-required now ON; prod
    surfaces live), CLAUDE.md Phase 9 (9.5 ✅).

**Deferred past 9.5d (note, don't silently forget):** deletion/data-subject endpoint (docs/11 §3.1),
per-IP/edge rate-limiting + captcha (§3.3 — OAuth bounds abuse meanwhile), spend-trend observability/alerting
(§3.5). Backups: Neon provides PITR; confirm retention.

---

## For the next chat (post-reset)
Read `docs/INVARIANTS.md` → WORKLOG top → **this file**. Find the next ☐ block above; its detail (9.5a) or
sketch (9.5b–d, refine before building) is the spec. Locked decisions are fixed unless Hayden reopens them.
