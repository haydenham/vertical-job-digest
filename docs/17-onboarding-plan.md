# Onboarding overhaul — plan of record (beta-hardening, D-082)

*Working execution plan for the onboarding overhaul, scoped by **D-082**. Read
`docs/INVARIANTS.md` → `WORKLOG.md` top → this file to continue after a chat reset. Memo-tier
plan (authority order unchanged): when a PR lands, its decisions go to `DECISIONS.md`, live
rules to `docs/INVARIANTS.md`, and this file's checkboxes get ticked.*

## What this is

The first real private-beta user hit onboarding friction end-to-end: an outdated résumé forced
a reupload nobody had designed the UX for, he reported being **stuck on the upload page**, and
found the dashboard toggles ambiguous. The fresh-signup path had never been walked by the
builder (his test users were pre-onboarded), so this block is also the fresh-account leg of the
docs/15 Day-3 bug shakeout. Exploration (2026-07-13) found a concrete root cause for every
complaint — see D-082 for the decision record. Scope decisions were run through Hayden
2026-07-13.

**Decisions locked (Hayden, D-082):**

- **Backend backfill-status signal** — stamp backfill start/finish on the profile, expose via
  `/api/me`, drive the dashboard's "matching in progress" display from it. Supersedes D-057's
  "no backend status endpoint" clause (the bounded client poll stays as the consumer).
- **Reupload = instant 5-day re-match + nightly heals the rest, surfaced honestly.** No
  immediate full re-match (~$3/event against the $5 daily ceiling, D-057); the uncapped nightly
  already re-matches the full open set against a new résumé version. The UI says so instead of
  going silently near-empty.
- **Tutorial = first-run welcome slides** (multi-step dialog reusing the `PostingPanel`
  pattern), seen-flag in `localStorage`, re-openable via a "?" nav button. Not a coach-marks
  tour.
- **3 PRs**: bug-fix tier → progress signal → tutorial + toggle clarity. PR 1 has no design
  sign-off dependencies; PRs 2 and 3 are independent of each other.

**Constraints that hold throughout:**

- D-064 one-vertical + D-065 route guards unchanged; résumé upload stays the SPA's only write
  surface (D-057).
- Backend contract changes are confined to PR 2 (additive: two nullable profile columns + one
  derived `/api/me` field); `/api/postings` never moves.
- Gates per repo standard (D-021): backend ruff/format/mypy/import-linter/pytest + frontend
  eslint/tsc/vitest where touched; bug fixes start with a failing regression test; branch-only —
  Hayden commits/PRs. `main` auto-deploys on merge (D-068).

---

## PR 1 — upload/onboarding bug-fix tier (branch `fix/onboarding-upload`)

*The "stuck on upload page" cluster. Frontend-only except one backend regression test — no
migration, no API change.*

- [ ] **Visible upload progress:** a busy notice with spinner ("Uploading and starting your
  matches…") while the POST runs — not just a button-label swap (`Upload.tsx`).
- [ ] **Upload timeout + friendly transport errors:** `AbortController` timeout (~30s) on
  `uploadResume` (`api.ts`); abort and network failures get friendly leads in the form error
  (no more raw `TypeError: Failed to fetch`).
- [ ] **Post-upload robustness (the commit-point rule):** after a 202 the upload can no longer
  present as failed. The `/api/me` re-probe retries bounded (~4 attempts, backoff) until the
  profile lands, then navigates; the probe is **silent** (no global `loading` flip, so the form
  no longer blanks to "loading…" mid-submit — the literal stuck-page report). If the probe
  never confirms, a calm "résumé uploaded — open your dashboard" state replaces it (full-page
  nav re-probes auth). Kills the spurious-error and bounce-back-to-onboarding races
  (`Upload.tsx:69-82`, `AuthProvider.tsx`; `refresh()` now returns the fetched `Me`).
- [ ] **Back navigation on `/upload`** (update mode): "← Back to dashboard" link — previously
  the only exit without submitting was the logo.
- [ ] **Reupload honesty copy (cheap half):** update-mode blurb → recent roles re-match within
  minutes; full refreshed results after tonight's run. (The live progress display is PR 2.)
- [ ] **Dashboard poll no longer blanks:** keep previous data while a refetch/poll tick is in
  flight; the bare "loading…" notice only renders before first data (`Dashboard.tsx`).
- [ ] **Backend regression test (unpinned path):** POST `/api/profiles` twice through the API —
  changed bytes → 202 + new `resume_version` + new active profile + backfill re-triggered;
  same bytes → idempotent; (second-vertical 409 already pinned).
- **DoD:** frontend + backend gates green · RTL tests for retry-probe/timeout/back-link/
  keep-data · fresh-flow walkthrough in headless Chrome (signup → upload → dashboard; reupload
  → back-nav) with before/after screenshots in the PR body.

## PR 2 — matching-progress signal (backend + frontend) ✅ (built 2026-07-13, branch `feat/backfill-status`)

*Two refinements from the plan sketch, recorded here (D-082 governs, no new ADR): (a) the **started
stamp moved to the upload endpoint** (before `background.add_task`) — the 202 returns before the
background task runs, so stamping only inside `run_backfill` would race the SPA's immediate
`/api/me` probe; (b) **staleness is applied server-side** in the status derivation (one clock, one
place, unit-testable) rather than by the client as first sketched — the client stays dumb.*

- [x] **Migration (Alembic `a06b99424c4c`):** `profiles.backfill_started_at` +
  `backfill_completed_at` (nullable UTC), additive. Rehearsed on a local DB copy;
  **run manually on Neon before merge** (D-068); both-dialect CI covers the schema.
- [x] **Stamps:** endpoint stamps `started` pre-schedule; `run_backfill` stamps `completed` in a
  `finally` (lands even when every candidate fails — per-posting isolation means the run itself
  finished). Only a hard process kill skips it; the staleness guard covers that.
- [x] **`GET /api/me`:** profile gains derived `backfill_status: "running" | "done" | null`
  (`derive_backfill_status` in `db/profiles.py`): done ⇔ `completed >= started` (the
  reupload-ordering rule — a reactivated row carries the previous run's completion stamp);
  stale running (> `BACKFILL_STALE_AFTER`, 10 min) reads done (crash guard); never-stamped → null.
- [x] **Dashboard:** poll keys off the real status (survives refresh, fires on reupload;
  `justOnboarded` router state no longer read — the pre-202 stamp makes it unnecessary).
  Persistent "Matching in progress — results update live" banner while running, shown **above
  existing rows too** (the reupload case); matched empty states distinguish "Matches appear here
  as they're computed." (running) from "No matches yet — full results after tonight's run." (done).
  No client timeout — the server's staleness guard bounds the poll.
- [x] **INVARIANTS:** D-057 bounded-blind-poll line rewritten to the status signal + commit-point
  rules (D-082).
- **DoD met:** backend gates green (ruff/format/mypy/import-linter + pytest **518**, +12: stamp
  round-trip, 6 derivation cases incl. reupload-ordering + staleness, completion-on-failure,
  /api/me per state, endpoint-stamps-before-schedule) · frontend gates green (eslint + tsc +
  vitest **85/85**; Dashboard suite reworked to the status-driven poll) · migration rehearsed on
  a migrated local copy · live headless-Chrome walkthrough: fresh signup → done state; banner
  over real rows; **running → done poll flip observed live** (stamped `completed` mid-session,
  banner cleared on the next tick without a reload); no console errors, no overflow.

## PR 3 — welcome-slides tutorial + toggle clarity

- [ ] **First-run dialog** on the dashboard (reuses the `PostingPanel` dialog pattern:
  `role="dialog"`, Esc/click-away): 3–4 slides — what Rolefeed does (nightly diff + digest) ·
  Matched vs All-cleaned views · recency windows + row click/detail panel · updating your
  résumé (and what to expect when you do). Shown once per browser (`localStorage`
  `rolefeed.tour.seen`); a "?" nav button reopens it anytime.
- [ ] **Toggle clarity** (`Controls.tsx`): `title` tooltips on every window/view toggle; label
  copy tweaks (e.g. "matched" → "Matched for you", "all cleaned" → "All in-scope") — **exact
  copy is a Hayden sign-off at PR-3 execution**.
- [ ] RTL tests: first-run show / dismiss / persist / reopen via "?".
- **DoD:** frontend gate green · slide-by-slide screenshot pass at 1440/720.

---

## Out of scope (parked, tracked)

- **Coach-marks/spotlight tour** — welcome slides chosen instead (D-082); revisit if slide
  comprehension proves weak.
- **Immediate full re-match on reupload** — rejected for now (~$3/event vs the $5 daily
  ceiling; nightly heals within a day). Revisit only with per-user rate limits + budget rework.
- **Backend persistence of the tutorial-seen flag** — localStorage is enough for beta.
- **Mobile pass** — already parked (D-080).
- **Robotics vertical config** — Hayden's, pre-beta; the live landing advertises it while the
  picker can't offer it until the config lands.
- Deleting the stale `origin/docs/onboarding-and-shipping-plan` remote branch (its docs/13
  content is on `main`) — Hayden's call.
