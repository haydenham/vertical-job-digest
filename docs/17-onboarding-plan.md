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
- **3 PRs**: bug-fix tier → progress signal → tutorial + toggle clarity. PRs 1 and 2 are
  merged (#78/#79); the D-083 production follow-up is merged (#80); PR 3 is merged (#82).

**Constraints that hold throughout:**

- D-064 one-vertical + D-065 route guards unchanged; résumé upload stays the SPA's only write
  surface (D-057).
- Backend contract changes are confined to PR 2 (additive: two nullable profile columns + one
  derived `/api/me` field); `/api/postings` never moves.
- Gates per repo standard (D-021): backend ruff/format/mypy/import-linter/pytest + frontend
  eslint/tsc/vitest where touched; bug fixes start with a failing regression test; branch-only —
  Hayden commits/PRs. `main` auto-deploys on merge (D-068).

---

## PR 1 — upload/onboarding bug-fix tier ✅ (merged #78, 2026-07-13)

*The "stuck on upload page" cluster. Frontend-only except one backend regression test — no
migration, no API change.*

- [x] **Visible upload progress:** a busy notice with spinner ("Uploading and starting your
  matches…") while the POST runs — not just a button-label swap (`Upload.tsx`).
- [x] **Upload timeout + friendly transport errors:** `AbortController` timeout (~30s) on
  `uploadResume` (`api.ts`); abort and network failures get friendly leads in the form error
  (no more raw `TypeError: Failed to fetch`).
- [x] **Post-upload robustness (the commit-point rule):** after a 202 the upload can no longer
  present as failed. The `/api/me` re-probe retries bounded (~4 attempts, backoff) until the
  profile lands, then navigates; the probe is **silent** (no global `loading` flip, so the form
  no longer blanks to "loading…" mid-submit — the literal stuck-page report). If the probe
  never confirms, a calm "résumé uploaded — open your dashboard" state replaces it (full-page
  nav re-probes auth). Kills the spurious-error and bounce-back-to-onboarding races
  (`Upload.tsx:69-82`, `AuthProvider.tsx`; `refresh()` now returns the fetched `Me`).
- [x] **Back navigation on `/upload`** (update mode): "← Back to dashboard" link — previously
  the only exit without submitting was the logo.
- [x] **Reupload honesty copy (cheap half):** update-mode blurb → recent roles re-match within
  minutes; full refreshed results after tonight's run. (The live progress display is PR 2.)
- [x] **Dashboard poll no longer blanks:** keep previous data while a refetch/poll tick is in
  flight; the bare "loading…" notice only renders before first data (`Dashboard.tsx`).
- [x] **Backend regression test (unpinned path):** POST `/api/profiles` twice through the API —
  changed bytes → 202 + new `resume_version` + new active profile + backfill re-triggered;
  same bytes → idempotent; (second-vertical 409 already pinned).
- **DoD met:** frontend + backend gates green (frontend 83/83; backend 506) · RTL tests for
  retry-probe/timeout/back-link/keep-data · fresh-flow walkthrough in headless Chrome
  (signup → upload → dashboard; reupload → back-nav) with before/after screenshots.

## PR 2 — matching-progress signal (backend + frontend) ✅ (merged #79, 2026-07-13)

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

### PR-2 post-merge incident + hotfix (D-083)

PR #79 merged and deployed before production Neon actually reached `a06b99424c4c`. The migration
had been run as a bare `uv run alembic upgrade head`; Alembic does not load `.env`, so that command
upgraded the default local SQLite DB. On the new Cloud Run revision, an existing user's `/api/me`
hit the missing `backfill_started_at` column and returned 500. `AuthProvider` then collapsed that
non-401 failure to logged-out, making the successful Google login appear to redirect to Landing.

**Production recovery completed 2026-07-13:** explicitly exported the Secret Manager Neon
`VJA_DATABASE_URL`, upgraded to `a06b99424c4c`, and restored `/api/me`. Follow-up branch
`fix/onboarding-auth-failure` added the D-083 production startup guard (known-behind schema → new
revision never becomes ready; unknown newer revision allowed for rollback), separates auth-probe
errors from 401 with a retry state, guards `/login` for existing sessions, and corrects the
frontend upload response's `resume_version` from number to string. **Merged as PR #80; PR 3 was
then built on `feat/onboarding-tutorial`.**

## PR 3 — welcome-slides tutorial + toggle clarity ✅ (merged #82)

- [x] **First-run dialog** on the dashboard (reuses the `PostingPanel` dialog pattern:
  `role="dialog"`, Esc/click-away). Approved four-slide copy (D-085):
  1. **Your Rolefeed, updated nightly** — curated employers, nightly changes, verified links,
     and the morning digest.
  2. **Matched for you** — recommendations for the current résumé, including honest fits and
     gaps.
  3. **Explore every in-scope role** — explain All in-scope and the recency windows.
  4. **Open details and keep your résumé current** — row details/apply, recent-role re-match,
     and full completion through the nightly.
  Shown once per browser (`localStorage` `rolefeed.tour.seen`); a "?" nav button reopens it.
  Controls = **Skip · Back · Next · Start exploring**.
- [x] **Toggle clarity** (`Controls.tsx`): display labels = **Matched for you / All in-scope**
  and **New today / 1 week / 2 weeks / All open**; every toggle gets a concise `title`
  explaining its exact D-030/D-045 semantics.
- [x] **Put the table-use hint where it is visible:** move
  "Click a row for details · read-only · updates nightly" from the footer to immediately above
  the table/results area.
- [x] **Human vertical display:** render the internal `aviation_software` slug as **Aviation
  Technology** through `verticalCopy()` on the dashboard and locked résumé-update screen, and keep
  the landing vertical card consistent; the raw key stays out of user-facing UI while the
  config/API/DB slug remains unchanged. (The broader landing-copy rewrite remains a separate PR.)
- [x] RTL tests: first-run show / dismiss / persist / reopen via "?"; forward/back, final CTA,
  Escape, backdrop, and Skip are also pinned.
- **DoD met:** eslint + `tsc -b --noEmit` + vitest **95/95** + production build green;
  headless-Chrome slide-by-slide pass at 1440/720 plus the post-dismiss dashboard at both widths
  (no horizontal overflow, raw slug, console errors, or page errors; guide verified above table).

## Accepted follow-ups after PR 3 (D-085)

- **Landing-page copy pass ✅ (built on `feat/landing-copy`; awaiting Hayden's commit/PR):** stop the
  three thesis cards, How it works, and
  Why I built this from repeating the same claim. Cards = user benefits; How it works = actual
  pipeline mechanics; founder story = Hayden's recruiting problem and product thesis. Broaden
  outward language from *software roles* to *technology roles* so analyst/data roles fit the
  promise. Internal vertical slugs stay stable. The approved implementation broadens the hero to
  **technology jobs**, gives the cards three distinct user benefits, makes the three steps the
  curate → fetch/diff/verify → extract/match/deliver pipeline, and uses Hayden's new founder
  description with a direct email link.
- **Résumé-reupload abuse guard (separate backend/security PR):** first upload stays allowed;
  identical-content reuploads return success without scheduling another backfill; a changed
  résumé is limited to one reupload per user per rolling 24 hours, server-enforced with 429 +
  `Retry-After`.
- **LLM-cost Block 2:** diagnose the observed posting new/closed identity churn before building
  Anthropic Message Batches. If steady-state extraction remains material after the correctness
  fix, batch extraction first; matching is already highly cache-efficient.

---

## Out of scope (parked, tracked)

- **Coach-marks/spotlight tour** — welcome slides chosen instead (D-082); revisit if slide
  comprehension proves weak.
- **Immediate full re-match on reupload** — rejected for now (~$3/event vs the $5 daily
  ceiling; nightly heals within a day). Revisit only with per-user rate limits + budget rework.
- **Backend persistence of the tutorial-seen flag** — localStorage is enough for beta.
- **Mobile pass** — already parked (D-080).
- **Robotics vertical config** — Hayden's, pre-beta. Hayden reaffirmed 2026-07-14 that the live
  landing should keep the Robotics promise because the vertical will be added; the picker still
  cannot offer it until the config lands.
- Deleting the stale `origin/docs/onboarding-and-shipping-plan` remote branch (its docs/13
  content is on `main`) — Hayden's call.
