# Beta-hardening plan — the pre-broad-invite week

*Working execution plan for the beta-hardening effort that follows 9.5d go-live + the onboarding overhaul.
Lives in the repo because chats reset between days — a fresh session should read `docs/INVARIANTS.md` →
`WORKLOG.md` top → **this file** and be able to continue. This is a **plan**, not an invariant source: when
a day lands, its decisions go to `DECISIONS.md`, the live rules to `docs/INVARIANTS.md`, and this file's
checkboxes get ticked. Authority order unchanged (build specs `docs/04+` > `CLAUDE.md` > memos); this doc is
a memo-tier working plan. Scope of record: **D-072.***

**Where we are.** Go-live infra is done (D-067) and its closeout is **complete** — the app is live on
`https://role-feed.com`, Postgres on Neon, auth enforced, the nightly Job + Scheduler running, digests
**sending from the verified `digest@role-feed.com`** (email E2E ✅), and the `/security-review` ✅. CI/CD is
live (D-068 — merge-to-`main` auto-deploys). The onboarding overhaul (D-065) shipped and **real private
users are signed up and working**. So the launch blockers are cleared; this week is about making the beta
*good*, not making it *possible*.

**Shape.** Six items, **one day each**, so every fix is verified sound before the next starts. Order is
Hayden's; the only hard dependency is **Day 2 → Day 4** (the discovery run produces the per-run cost number
the scaling day consumes). Each day's Definition of Done is the repo standard (D-021): green gates
(ruff/format/mypy/import-linter/pytest, + frontend eslint/tsc/vitest where the change touches `frontend/`) +
a human-read diff + updated docs, on a branch → PR.

---

## Day 1 — UI rework (SCOPED — D-080; plan of record: `docs/16-ui-rework-plan.md`)

Scoped 2026-07-12 in a planning session (every decision Hayden's). The timeboxed reference-pick resolved to
**Linear**; the item expanded from one day to a **4-PR block, strict merge order** — see `docs/16` for the
full plan + per-PR DoD. Summary:

- **PR 0** — design-language foundation: DESIGN.md v2 ("softer, more premium dark"; accent/fonts/terminal
  motifs all up for replacement, Hayden signs off accent + font from screenshots) + `theme.css` tokens +
  app shell.
- **PR 1** — full Linear-style marketing landing (hero · how-it-works · verticals · footer; CSS-built
  product mock, no binary asset).
- **PR 2** — login/onboarding polish (auth card, descriptive vertical cards, drag-drop upload; fixes
  Login's stale "browse without signing in" copy — false since D-067).
- **PR 3** — dashboard rework: row-level match info (verdict/score + rationale snippet without a click),
  Linear-style side-panel detail, client-side sortable columns + text filter. No API contract change —
  `/api/postings` already returns the full set unpaginated.
- **Watch (unchanged):** Rolefeed brand; D-065 route guards; one vertical per user (D-064) — no cross-user
  vertical picker. **Out:** mobile pass (deferred), keyboard nav (not selected).

## Day 2 — Discovery agent: live run + supporting tooling

Run `vja-discover` → `vja-review` for real (the still-pending 10.1/10.2 live smoke folds in here), landing a
good batch of new companies with **minimal manual input**. This is where the ready-but-OFF weekly schedule
earns its enable decision.

- **Scope:**
  - Run the live `vja-discover --vertical grid_power_software` loop (needs `OPENAI_API_KEY` + web search;
    Hayden-run) → review/approve via `vja-review`. Operator guide: `docs/14`.
  - **Coverage ledger** — a way to see fetchable vs. parked vs. proposed across the universe, so "how much do
    we actually cover" is a number, not a guess.
  - **Low-signal pruning** — drop/retire noisy or irrelevant employers the run surfaces (the agent adding
    companies is exactly when noise creeps in).
- **Produces:** the **real per-run cost** of discovery → the input that gates flipping the weekly schedule from
  ready-but-OFF to ON (D-071), and the LLM-spend numbers Day 4 needs.
- **DoD:** new `active` employers in the DB (surfacing on the next nightly); ledger exists; measured per-run
  cost recorded (WORKLOG + Day 4). Any new tooling gets tests.

**First live run — 2026-07-10 (partial):** after fixing a self-starving tool budget (searches/fetches 8→20/16,
`$` ceiling 2→4; the old per-request `max_uses`==cumulative-cap coupling ended the run after one blocked turn —
see WORKLOG) the loop did **real oblique sourcing**: 5 candidates off the Energy Impact Partners portfolio
(GridBeyond, GridX, Emerald AI, CivilGrid, eSmart Systems), all landing `proposed`/`layer2` (GridBeyond's ATS
confirmed **BambooHR** — the fetcher is now built, with activation pending deployment + D-077 review;
the other four are JS-rendered/unresolved). **New binding
constraint (feeds Day 4):** the run stopped on an **external web-tool rate limit (429s), not our `$`/tool caps** —
so discovery *yield* is now gated by the Anthropic `web_search`/`web_fetch` rate limit, not our budget. It
completed only ~1 of ~3 planned source waves. Before flipping the weekly schedule ON, decide whether that limit
is per-minute (→ add pacing/backoff between waves) or a hard quota. Triage of #91–95 + the BambooHR-fetcher
question are still open.

**Provider/ATS hardening branch — 2026-07-10:** the next run moves discovery only to GPT-5.6 Terra
(D-074). It replaces the single Claude loop with three independently capped source waves and reserves a
separate four-action resolver for each of at most five candidates. Canonical provider-URL evidence plus
the existing validate-by-fetch gate is required before a supported ATS is stamped; confirmed unsupported
providers and typed failure reasons remain visible in proposal notes. The first Terra live run now supplies
the cost/yield/rate-limit evidence that still gates schedule enablement.

## Day 3 — Bug shakeout

Fix bugs surfaced by real private-user usage and the Day-2 run. Bug fixes **start with a failing regression
test** (D-021).

- **Scope:** whatever real usage exposes — onboarding edge cases, digest content, dashboard windows, fetcher
  drift.
- **Proposed sub-item (Hayden's call at execution):** **basic observability/alerting on the nightly** so a
  silent failure doesn't strand private users who now depend on the digest. `docs/11` deferred this; the
  minimum is "if the nightly fails or sends nothing unexpectedly, Hayden finds out." Small, but it's the
  difference between "beta" and "beta that embarrasses you."
- **DoD:** a regression test per fix; green gates; WORKLOG notes each bug + fix.

## Day 4 — Scaling plan (analysis + guardrails)

A written scaling assessment across every external dependency, **now including Anthropic/LLM spend as a fifth
pillar** (Hayden's call — folded in rather than a separate day).

- **Five pillars:**
  1. **Neon** (Postgres) — connection limits, autosuspend behavior, storage/compute tier, backups.
  2. **GCP / Cloud Run** — service + Job scaling, concurrency, cold starts, cost at N users.
  3. **Resend / deliverability** — sending volume limits, domain reputation, bounce handling on the verified
     `role-feed.com` sender.
  4. **Google OAuth** — consent-screen/verification status, user cap, quota.
  5. **Anthropic / LLM spend** — read the **real nightly token numbers** now persisted to `pipeline_runs`
     (D-069's four token columns) and decide the **parked Batch API "Block 2"** (extraction is input-bound and
     uncacheable; the Batch API is the lever, not caching). Set spend guardrails beyond the existing backfill
     cap + daily ceiling (D-057).
- **DoD:** a written scaling doc (thresholds + "what breaks first" + the Block-2 decision); any guardrail
  config that's cheap to land now. Reads `docs/11` (portability ledger) as the baseline.

## Day 5 — More fetchers

Expand coverage, **demand-ranked** (D-076 — reordered from "Phenom next" after the discovery runs + live
probes; the demand ledger now lives in `docs/07` — the Day-2 "coverage ledger" first edition). Order:

1. **Workday config onboards: Southwest + Thales ✅** — both live-verified on 2026-07-11 through the
   existing fetcher (SWA `swa:wd1:external`, 47 jobs; Thales `thales.wd3`/`Careers`, 2,000 global jobs).
   Config-only, zero code; discovery-expanded production coverage 64 → 66 fetchable after the seed import.
2. **Paylocity fetcher ✅ (activation pending deploy)** — discovery demand #1 (4 waiting proposals:
   Veryon, Trax + 2 grid). Embedded
   `window.pageData` JSON, single-response guard + lazy detail — build notes in `docs/07` step 9.
   **The D-077 review-correction tooling rides with this block:** `vja-review set-ats` (validate-by-fetch,
   status untouched) + `list --provider` + the parked-re-approve bugfix (regression test first, D-021) —
   needed the moment this fetcher lands to activate its waiting proposals *and* to fix the proposals the
   agent misresolved (real Greenhouse companies parked `unknown`). Runbook: docs/14.
3. **Phenom fetcher ✅** — United (flagship aviation employer; Taleo underneath): `/widgets`
   refineSearch, paginate-or-fail on `totalHits` + `jobDetail` lazy detail; United live-verified and onboarded.
4. **BambooHR fetcher ✅ (activation pending deploy)** — slug-derived single-response JSON with
   `meta.totalCount` completeness, structured location fallbacks, constructed public apply URLs, and lazy
   detail returning only `result.jobOpening`. GridBeyond (`gridbeyond`) + Comply365 (`vistairhr`) remain
   discovery proposals until each passes the post-deploy D-077 `set-ats` validation and explicit approval
   (`docs/07` step 11); no seed rows were added.
5. **Post-audit re-rank (D-078, 2026-07-12):** a read-only audit of prod's 72 unfetched rows re-ranked
   what's next — (a) **no-code activations first**: six validated discovery rows via the D-077 runbook
   (Hayden runs; the audit chat has the exact commands) + the **Honeywell Oracle CSV onboard ✅** (landed
   this session; activates at the next seed import against Neon); then (b) **Pinpoint ✅** (D-079; clean
   `/postings.json`; Aurora seed onboarded, Aireon pending post-deploy D-077 activation) →
   **Radancy variants** (L3Harris JSON / NRG / American Airlines,
   up to +5) → **JazzHR** (+2) → **Jobvite** (+2) → **Taleo** (Bell + Textron Aviation, +2). Full ledger +
   per-fetcher build notes: `docs/07` demand ledger + steps 12–16. Projected coverage: 63 → ~72 no-code →
   ~83 with builds 1–4.

Cheap hardening that rides along regardless: extend `discover._PROVIDER_HOST_MARKERS` with
`paylocity`/`kula`/`gusto`/`rippling`/`trinet_hire`/`trakstar`/`pinpoint`/`phenom` markers so future
discovery runs type these providers deterministically instead of burning resolver actions.

- **Scope:** generic platform fetchers only (D-017 — no per-company scrapers), config-only onboarding of the
  tenants each unlocks. Parity with the list-only fetchers where applicable (`extract._DETAIL_RESOLVERS`).
- **DoD:** fetcher + tests (fixtures, not live) green; employers onboarded config-only; coverage count updated
  in the docs/07 ledger + CLAUDE.md Phase 8 line; fixed-`ats_type` proposals promoted via `vja-review`.

---

## Not in this week's scope (parked, tracked)

- **Auto-approval + proposal-precision eval** for discovery (Phase 10 later — needs a real sample).
- **Non-employer `sources`** (HN/niche) discovery.
- **Enabling the weekly discovery schedule** — gated on Day 2's measured cost; flip is config, not code (D-031).
- **Moving `config/verticals/*.yaml` out of the image** (Path-A config) — premature per `docs/11` §5; revisit
  when Path-B redeploys actually hurt.
