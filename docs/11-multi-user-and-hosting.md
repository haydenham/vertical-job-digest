# Multi-User & Hosting Migration Ledger

*A **living checklist**, not a design doc. The product is single-user (the builder) on a local SQLite +
launchd setup today; the [D-025](../DECISIONS.md) hosting/Postgres cutover (~2 demo users incoming) is the
trigger that makes multi-user real. The purpose of this file is narrow: turn "a lot goes into a cloud
migration" into an **enumerated, trackable list**, and protect the **seams** that keep single-user
assumptions from silently hardening before then.*

*Discipline: **document the seams now (cheap), build the machinery at the trigger.** Keep this honest with the
[kill criterion](../CLAUDE.md#kill-criterion-do-not-quietly-forget) — the product may not reach multi-user, so
nothing here justifies speculative scaffolding ahead of need. Each phase **appends** to §3 as new deferrals
appear and **checks off** items as the cutover lands.*

---

## 1. Already portable (decided + built — don't re-derive)

These are the usual migration-killers, and they're handled by deliberate decisions. Linked so we don't
re-litigate them under cutover pressure.

| Concern | Status | Where |
|---|---|---|
| **DB portability** | SQLite→Postgres is a URL swap + `alembic upgrade`, now **CI-verified on both dialects** (the suite re-runs on a `postgres:16` service via `VJA_TEST_DATABASE_URL`). SQLAlchemy **Core** + Alembic; enums are `VARCHAR+CHECK` (`native_enum=False`); `UTCDateTime` normalizes tz on both dialects; JSON via `sa.JSON`. | D-025, D-054, `src/vja/db/schema.py`, `src/vja/db/engine.py`, `tests/conftest.py`, `.github/workflows/ci.yml` |
| **Runtime/scheduler** | Scheduler is a swappable trigger. App logs to **stdout/stderr**; schedule time + secrets are **env config**, not code; macOS surface confined to `deploy/launchd/`. Cutover adds a `deploy/<platform>/` trigger. Postgres unlocks GitHub Actions cron. | D-031, `src/vja/nightly.py` |
| **Cost model scales with data, not users** | Server-side nightly batch; users only **read** precomputed results; each ATS endpoint hit once/day total regardless of user count. | D-005 |
| **Matching is multi-user-shaped already** | Push-batch keyed on `(posting, profile)`; `matches`/`digests`/`profiles` are per-user rows; `employers`/`postings` are shared (shared coverage is the whole point). | D-006, `src/vja/db/schema.py` |
| **Identity seam chosen** | "A user is resume+vertical+email." Digest recipient already resolves from `profiles.user_email`; `VJA_DIGEST_RECIPIENT` repurposed as the ops/alert address. | D-027, D-037 |
| **Resume input seam** | Everything downstream reads `profiles.resume_text`; non-text formats (PDF/OCR) are a signup-time adapter at the upload boundary — no schema/matching impact. | D-033 |

**Net:** the persistence, runtime, and cost layers are portable today. The gap is the entire user-facing /
identity layer — which mostly **doesn't exist yet**, so there's little to make portable. The risk is therefore
about *not baking in single-user assumptions* in the surfaces we build next (§2), not about retrofitting what's
already decided.

## 2. Seams we are actively preserving (promises each phase must not break)

Concrete, low/zero-cost rules adopted now so the cutover is "add a layer," not "rewrite."

- **Phase 6 dashboard API is `(vertical, profile_id)`-parameterized.** The read API resolves data by explicit
  vertical + profile, never "the one active profile." Today a thin default picks the single active profile;
  multi-user adds *resolve profile from authenticated session → filter*, not an API redesign. Per-user rows
  (`matches`/`digests`) stay row-scoped; shared rows (`employers`/`postings`) stay global. *(Status: ✅ adopted
  in Phase 6 B1 — `_resolve_profile` in `src/vja/api/app.py`: explicit `profile_id` or single-active default;
  404 none, 409 ambiguous. D-041. **Auth plugged in 9.2** — `_resolve_profile(…, user)` now resolves the
  authenticated user's own profile, 403 on another's `profile_id`; enforcement gated by `VJA_AUTH_REQUIRED`. D-055.)*
- **No live external calls from user-facing surfaces** (D-005). The dashboard reads the DB only; it never
  triggers a fetch/LLM call. Keeps the read path safe to expose publicly without a cost/abuse surface.
- **PII lives only in `profiles`/`matches`/`digests`.** Don't denormalize `user_email`/`resume_text` into
  shared tables — keeps the future data-isolation + deletion story tractable (§3).
- **Secrets via env/`.env` only**, never in code or repo (existing CLAUDE.md policy) — so a platform secret
  store is a config swap.

## 3. Deferred work (build at the D-025 trigger) — enumerated

Not solved now. Listed so the cutover is a checklist, not a discovery exercise. Unchecked = not started.

### 3.1 Security & PII *(highest stakes — flagged early on purpose)*
- [ ] `resume_text` and `user_email` are **PII**. Define at-rest handling, access control, and retention once
      hosted. DB is never publicly exposed (CLAUDE.md) — keep that true behind a network boundary in cloud.
      *(9.3: the upload adapter (`vja.resume`) never logs the text or raw bytes; at-rest encryption + access
      control + retention still 9.5. D-057.)*
- [ ] **Deletion / data-subject requests:** a user must be able to have their `profile` + derived
      `matches`/`digests` removed. Cascade story (postings/employers are shared and stay).
- [ ] **Backups & DR** for Postgres once it holds real user data (today `vja.db` is disposable).
- [ ] **Transport/security review** of any exposed surface (the FastAPI read API) before it leaves localhost
      — run `/security-review` on the cutover diff.

### 3.2 Auth & identity
- [x] **`users` table + Google OAuth login + signed-cookie sessions** (D-055, Phase 9.2). Authlib OIDC →
      `SessionMiddleware`; `users` (`google_sub`/`email`/`name`) anchored on the D-027 email seam (first
      login adopts the email-only seed identity + backfills `profiles.user_id`). *(Prod OAuth redirect URIs +
      cookie hardening `https_only`/`SameSite` still deferred to the 9.5 deploy.)*
- [x] **Authz:** the read API resolves the profile from the authenticated user — the §2 seam, now plugged
      (`_resolve_profile(…, user)`: own-profile resolution, 403 on another's `profile_id`). *Hard*
      enforcement is gated by `VJA_AUTH_REQUIRED` (default off), **stays off through 9.4** (the Rolefeed SPA
      dashboard is anonymous-readable; only `/upload` needs login), flips on at the 9.5 deploy. (D-055, D-058)
- [x] **Frontend login + upload UI (9.4, D-058):** the Rolefeed SPA (`react-router-dom`, `/`·`/login`·`/upload`)
      sends credentialed fetches so the session resolves the user's own profile; résumé-upload form over
      `POST /api/profiles` with optimistic backfill UX. *(9.5a/D-059 built the cookie hardening, the HTTPS
      OAuth callback URI, and the SPA deep-link catch-all — all env-gated; the auth-gate flip + prod
      redirect-URI registration land at the 9.5c/d deploy.)*
- [ ] Multi-profile-per-user shape (one user, both verticals) vs. the current one-profile-per-(vertical) view.
      *(1-vertical/user is the accepted default; the `profiles.user_id` FK already supports 1:many when wanted.)*

### 3.3 Cost & abuse control
- [x] **Signup-triggered backfill is the first place user action drives LLM spend** (the D-006 on-demand
      exceptions: signup backfill, resume-update re-match, deep-dive). **Guarded in 9.3 (D-057):** a
      per-backfill candidate cap (`VJA_BACKFILL_MAX_POSTINGS`) on top of the 5-day window (D-039), plus a
      global daily spend ceiling (`VJA_DAILY_LLM_BUDGET_USD`, checked pre-kickoff → 429; estimated from the
      day's match count, no per-match ledger). (The read-only dashboard never drives matching — D-005/D-041 —
      so it adds no cost surface here.)
- [ ] Rate limiting on the API + write endpoints. *(9.3 ships the cost ceilings above; per-IP/per-user
      request rate-limiting + captcha + email-verify are deferred to the 9.5 edge — Cloudflare/managed —
      since OAuth already bounds signup to real Google accounts. D-057.)*

### 3.4 Email deliverability
- [ ] D-029's sandbox sender (`onboarding@resend.dev`) only delivers to the Resend account owner. Real
      recipients need a **verified sending domain** (SPF/DKIM). A digest in spam is no product.

### 3.5 Live migrations & operations
- [x] **Containerized as one multi-stage image** (D-060, Phase 9.5b): `Dockerfile` builds the SPA (node stage)
      + installs the package non-editable (`uv` runtime), serving the SPA same-origin via `VJA_FRONTEND_DIST`.
      Two run targets from the one image — `vja-api` (service) + `vja-nightly` (job, entrypoint override). No
      secrets baked in (runtime env). Local prod-parity smoke passes; push/deploy to Artifact Registry + Cloud
      Run is 9.5c/d.
- [x] **Migrations validated on Postgres** — the full migration chain (`alembic upgrade head`) and the suite
      run on `postgres:16` in CI (D-054, Phase 9.1). *(The backward-compat discipline below is still pending —
      this only proves the schema builds + round-trips on PG, not that future migrations are non-destructive.)*
- [ ] Once Postgres holds user data, migrations must be **backward-compatible** (no destructive drops without a
      data path) — different discipline than the current disposable-DB era.
- [ ] **Observability beyond the failure email:** `pipeline_runs` is a solid audit start (D-031); cloud wants
      monitoring/alerting on run health, send failures, and LLM spend trend.
- [ ] **Secrets store** on the host platform (env vars / vault) replacing the local `.env`.

## 4. The trigger

The cutover is driven by **hosting for demo users (~2 weeks out, D-025)**, not by load. When it fires, this
ledger becomes the work breakdown: §3.1 (security/PII) and §3.2 (auth) gate any public exposure; §3.3–3.5 ride
along. Until then: keep the §2 seams, append new deferrals to §3, and build nothing here speculatively.
