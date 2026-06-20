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
| **DB portability** | SQLite→Postgres is a URL swap + `alembic upgrade`. SQLAlchemy **Core** + Alembic; enums are `VARCHAR+CHECK` (`native_enum=False`); `UTCDateTime` normalizes tz on both dialects; JSON via `sa.JSON`. | D-025, `src/vja/db/schema.py`, `src/vja/db/engine.py` |
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
  (`matches`/`digests`) stay row-scoped; shared rows (`employers`/`postings`) stay global. *(Status: to adopt
  in Phase 6 B1.)*
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
- [ ] **Deletion / data-subject requests:** a user must be able to have their `profile` + derived
      `matches`/`digests` removed. Cascade story (postings/employers are shared and stay).
- [ ] **Backups & DR** for Postgres once it holds real user data (today `vja.db` is disposable).
- [ ] **Transport/security review** of any exposed surface (the FastAPI read API) before it leaves localhost
      — run `/security-review` on the cutover diff.

### 3.2 Auth & identity
- [ ] No `users` table, no sessions, no signup/login. The whole authn layer is unbuilt.
- [ ] **Authz:** the read API must filter to the authenticated user's profile(s) — the §2 parameterization is
      the seam this plugs into.
- [ ] Multi-profile-per-user shape (one user, both verticals) vs. the current one-profile-per-(vertical) view.

### 3.3 Cost & abuse control
- [ ] **Signup-triggered backfill is the first place user action drives LLM spend** (the D-006 on-demand
      exceptions: signup backfill, resume-update re-match, deep-dive). Needs throttling + a per-user cost
      ceiling before any public signup. Backfill cap (≤14d, D-024) already bounds the set; this adds a
      rate/cost guard on top.
- [ ] Rate limiting on the API + any future write endpoints.

### 3.4 Email deliverability
- [ ] D-029's sandbox sender (`onboarding@resend.dev`) only delivers to the Resend account owner. Real
      recipients need a **verified sending domain** (SPF/DKIM). A digest in spam is no product.

### 3.5 Live migrations & operations
- [ ] Once Postgres holds user data, migrations must be **backward-compatible** (no destructive drops without a
      data path) — different discipline than the current disposable-DB era.
- [ ] **Observability beyond the failure email:** `pipeline_runs` is a solid audit start (D-031); cloud wants
      monitoring/alerting on run health, send failures, and LLM spend trend.
- [ ] **Secrets store** on the host platform (env vars / vault) replacing the local `.env`.

## 4. The trigger

The cutover is driven by **hosting for demo users (~2 weeks out, D-025)**, not by load. When it fires, this
ledger becomes the work breakdown: §3.1 (security/PII) and §3.2 (auth) gate any public exposure; §3.3–3.5 ride
along. Until then: keep the §2 seams, append new deferrals to §3, and build nothing here speculatively.
