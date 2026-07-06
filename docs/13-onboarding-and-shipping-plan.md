# Post-launch plan — thin shipping path + onboarding/auth-UX overhaul

*Working execution plan for the two blocks that follow the 9.5d go-live. Lives in the repo because chats
reset between blocks — a fresh session should read `docs/INVARIANTS.md` → `WORKLOG.md` top → **this file**
and be able to continue. This is a **plan**, not an invariant source: when a block lands, its decisions go to
`DECISIONS.md`, the live rules to `docs/INVARIANTS.md`, and this file's checkboxes get ticked. Authority order
unchanged (build specs `docs/04+` > `CLAUDE.md` > memos); this doc is a memo-tier working plan.*

**Status:** **9.5d go-live done** (D-067) — the app is live on `https://role-feed.com`, Postgres on Neon, auth
enforced (`VJA_AUTH_REQUIRED=1`), nightly Job + Scheduler running, digests sending from `digest@role-feed.com`.
**But the onboarding flow is broken for a fresh account** (see Phase B), which is a **blocker for inviting beta
users.** Two blocks close that gap, in order:

- **Phase A — thin scripted deploy** (ship reliably, ~30 min). Ships Phase B today. (D-066) — **✅ built**
  (`deploy/gcp/ship.sh`; DoD's no-op-rebuild deploy is Hayden-run, needs cloud creds).
- **Phase B — onboarding / auth-UX overhaul** (the real fix). (D-064, D-065)

Everything below the two blocks (discovery agent + review queue, coverage expansion, hardening) is the
**later roadmap** — captured here so it isn't lost, not scheduled yet.

---

## Context: what's broken and why (discovered 2026-07-06)

A fresh Google account was registered and walked through the live app. Every step was wrong:

1. **Logged out, the dashboard renders an error code**, not a login page. With `VJA_AUTH_REQUIRED=1`, `/`
   mounts `<Dashboard>` (`frontend/src/App.tsx:39`), which calls `/api/postings` → **401** → renders the 401
   string as `// 401…`. There's a `/login` page but **nothing routes to it**; "sign in" is only a small
   top-right nav link (`App.tsx:32`).
2. **After login, the dashboard 404s.** `active_verticals()` (`src/vja/db/profiles.py:131`) returns **every
   vertical with any active profile across all users**, sorted → `["aviation_software",
   "grid_power_software"]`. `Dashboard.tsx:22-31` takes `vs[0]` = **`aviation_software`** regardless of who is
   logged in. A grid user therefore requests `/api/postings?vertical=aviation_software`, `_resolve_profile`
   finds no aviation profile for their email → **404**.
3. **The vertical picked at upload has no effect** — nothing routes the dashboard to the *user's* vertical.
4. **No onboarding gate** — an authed user with no profile is dropped on a 404ing dashboard instead of being
   sent to upload.

**Root cause in one line:** the SPA treats "vertical" as a **global, cross-user picker** instead of a property
of the logged-in user. This contradicts the standing product policy — **one vertical per user** — which had
never been written down (the documentation/communication lapse this plan corrects; see D-064).

---

## Locked decisions (Hayden, 2026-07-06)

| Decision | Choice |
|---|---|
| **One vertical per user** | Always the policy. A user has exactly **one** active profile, in **one** vertical, chosen **once at signup**, **immutable** (no change path in v1; changing = manual/support). No cross-user vertical picker. (D-064) |
| **Target onboarding flow** | landing (static + login CTA) → Google auth → **one page: pick vertical + upload résumé** → routed to **their** dashboard. (D-065) |
| **Dashboard load** | *cleaned/all* renders immediately; *matched* shows a **loading indicator** while the backfill computes, resolved by a **bounded client-side poll** (no backend push/status endpoint); on timeout → *"full results after tonight's run."* (D-065) |
| **Landing page content** | **minimal placeholder** for now ("Rolefeed — sign in"); real marketing design later. |
| **Ship path** | a **thin scripted deploy** first (not full CI/CD), so Phase B ships today; merge-triggered CI/CD stays the deferred "9.6." (D-066) |
| **Account-chooser** | add `prompt="select_account"` to the OAuth redirect so Google stops silently reusing one session (folded into Phase B). |

---

## Phase A — thin scripted deploy

**Goal:** one idempotent command captures the manual cutover steps so no deploy forgets the `--platform
linux/amd64` flag, a secret mount, or the Job update. **Not** full CI/CD — that's the deferred 9.6.

**Do:** `deploy/gcp/ship.sh` (or a `Makefile` target) that:
1. `docker build --platform linux/amd64 -t "$IMAGE" .` (tag = `git rev-parse --short HEAD`).
2. `docker push "$IMAGE"`.
3. `gcloud run deploy rolefeed --image "$IMAGE" …` (service).
4. `gcloud run jobs update vja-nightly --image "$IMAGE" …` (keep the nightly on the same image — the D-031
   trigger-swap: one image, two run targets).
5. Print the serving revision + a one-line smoke (`curl $URL/api/health`).

Reuses the exact flags already proven in `deploy/gcp/CUTOVER.md` (secrets, SA, region). No secret **values** in
the script — it references Secret Manager by name, same as CUTOVER.

**DoD:** the script deploys a no-op rebuild end-to-end (service + job on the new image), health green, rollback
note (`update-traffic`) documented next to it. Docs: a short `deploy/gcp/` README line + this checkbox.

**✅ Built** (`deploy/gcp/ship.sh`, `feat/phase-a-ship-script`): build (`--platform linux/amd64`) → push →
capture prior revision → deploy service (full CUTOVER §5 config, no env-var writes → guards preserved) → update
`vja-nightly` Job → smoke (`/api/health` + anon `/api/postings?vertical=…` → **401**, the guard-survived
tripwire) → print rollback command. README section added. **Remaining for DoD:** Hayden runs the no-op-rebuild
deploy (needs cloud creds; not runnable in-sandbox — outward-facing prod deploy).

**Resolved (was open):** yes — the script snapshots the prior serving revision *before* deploy and prints the
`update-traffic` one-command rollback on success.

---

## Phase B — onboarding / auth-UX overhaul (the launch blocker)

### B-1 — Backend: make vertical a property of the user

- **New `GET /api/me`** → `{ user: {email, name}, profile: { vertical, resume_version } | null }`. The single
  source of truth the SPA routes on. Resolves the authed user's **one** active profile (D-064). No session →
  401 (auth is required now).
- **Enforce one-vertical-per-user at the write path.** `POST /api/profiles` (and/or `upsert_profile`) must
  **reject a second vertical** for a user who already has an active profile in a different one (409 or a typed
  error). Re-upload of the **same** vertical stays idempotent (résumé update → new `resume_version`, D-033).
  *Decision to confirm at build:* exact status + message; whether the seed's dual-profile anomaly is cleaned up
  first (below) so the constraint can't trip on legacy data.
- **`active_verticals()` stops driving per-user routing.** It stays for admin/internal use, but the dashboard
  no longer reads it to pick a vertical. (Supersedes the D-042 "`/api/verticals` drives the picker" reading.)

### B-2 — Frontend: real routes + guards

Routes and guard logic (react-router), driven by `/api/me`:
- **`/` — static landing page** (minimal placeholder + login CTA). Shown when logged out. **The dashboard is
  never rendered logged-out** (kills the 401-as-error leak).
- **Not signed in** anywhere gated → the landing / `/login`, never an errored dashboard.
- **Signed in, `profile === null`** → **`/onboarding`** (pick vertical + upload résumé, one page — reuse
  `Upload.tsx`, add the vertical selection, drop it from being a standalone afterthought).
- **Signed in, has a profile** → **`/dashboard`** for **their** vertical (from `/api/me`), **no picker**.
- **`prompt="select_account"`** on `/auth/login` so Google shows the account chooser (fixes the silent
  wrong-account login).

### B-3 — Dashboard load behavior

- *cleaned / all* renders immediately (it's the objective in-scope universe, same for any profile).
- *matched* shows a **loading indicator** on first paint after signup; a **bounded client-side poll**
  re-fetches `view=matched` every ~10s for ~2–3 min, swapping in results as the backfill lands. **No backend
  push, no status endpoint** (honors D-057). On timeout → *"matches update as they're computed — full results
  after tonight's run."* Manual refresh remains a fallback.

### B-4 — Data cleanup (prod write — needs Hayden's OK at build time)

The cutover seed loaded **two profiles under Hayden's main email** (aviation + grid) — the "two under one
email" anomaly that violates D-064. Deactivate one (`active = 0`; reversible, no cascade) so the constraint and
routing are clean. Keep whichever vertical Hayden wants his main account on; the other vertical goes on a
separate Google-backed email (Gmail **or** any email that is a Google account — Workspace / "use current email"
both work; a non-Google email cannot log in).

### Phase B DoD

Full Python gate (ruff/mypy/import-linter/`uv lock --check`/pytest on SQLite + CI Postgres) + the frontend gate
(eslint / `tsc --noEmit` / vitest). New tests: `/api/me` resolution + the one-vertical enforcement (API); the
three route-guard branches + the matched-poll timeout (vitest). Human-read diff. Docs: flip the INVARIANTS
dashboard/auth lines from "known defect" to the shipped behavior; DECISIONS status → done; tick here. Then
**deploy via Phase A** and re-run the fresh-account walkthrough end-to-end before inviting beta users.

---

## Beta onboarding checklist (once Phase B ships)

Not a code phase — the ops steps to get the two beta users + Hayden's second account on:
1. Add each **Google-account-backed** email as an OAuth **test user** (consent screen is External/Testing → only
   allow-listed emails can log in — a feature for a closed beta). Warn them about the "unverified app" screen
   (Advanced → proceed).
2. They visit `role-feed.com`, log in, land on onboarding, pick vertical + upload résumé, get their dashboard.
3. Confirm each user's vertical with them first (aviation vs grid).
4. Hayden's office wifi blocks the newly-registered domain (D-067) — he uses hotspot or has IT allowlist it;
   beta users on their own networks are unaffected.

---

## Later roadmap (captured, not scheduled)

From the 2026-07-06 planning discussion — sequence after beta users are on and giving feedback:

- **9.6 — full CI/CD** (merge-triggered auto-deploy), when deploy churn justifies replacing the Phase-A script
  (docs/11 §5).
- **Phase 10 — discovery agent + review queue.** The agent proposes new *employers* (`status=proposed`);
  **human approval stays required for the foreseeable future** (Hayden). The review surface (approve/reject/edit
  `proposed` rows) is the "approval-only, no commands" automation Hayden wants — build it so both the agent
  **and** manual curation feed the same queue. Already reserved as Phase 10 in `CLAUDE.md`.
- **Beta hardening** (Hayden's priority = **expand the employer universe** — the infra is strong, under-populated):
  - Finish **Phenom** (next fetcher — the airline portals; relevant to aviation beta users).
  - A **coverage ledger** (per vertical: fetchable / parked / Layer-2-only / dead) to make expansion a punch
    list, not a vibe.
  - **Prune low-signal employers** (`early_career_volume_estimate`) — total coverage of a *good* universe beats
    a bigger noisy one.
  - **Verify fetcher-health alerts actually fire in the cloud** (break one on purpose; confirm the ops email).
  - **Surface `pipeline_runs` as a daily ops line** (new / matched / $ spent / fetchers ok-failed) — you're
    spending real money nightly now.
  - **Deliverability watch** (inbox vs spam from the verified domain over several days).
  - **Match-feedback signal** (thumbs up/down) to grow the D-020 eval corpus from real verdicts.
  - Keep deferred: deletion/data-subject endpoint, edge rate-limiting, captcha (docs/11 §3 — OAuth + the
    test-user allowlist bound abuse for a closed beta).
  - **Let the two users' real feedback reorder this list** before over-building.

---

## For the next chat (post-reset)
Read `docs/INVARIANTS.md` → `WORKLOG.md` top → **this file**. Do **Phase A** (thin ship-script) first, then
**Phase B** (onboarding overhaul) — Phase B is the beta blocker. Locked decisions above are fixed unless Hayden
reopens them. Process: plan mode first, run decisions through Hayden, branch-only (he commits/PRs), DoD = green
gates + updated docs.
