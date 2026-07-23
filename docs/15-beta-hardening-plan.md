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

**Shape (amended by D-085).** D-072 said "six items" but enumerated **five workstreams**; this plan now names
that actual shape rather than preserving the counting error. The original one-day sizing also stopped being
useful when UI and onboarding each became multi-PR blocks. Work stays serial and reviewable; the only hard
dependency was **Day 2 → Day 4** (the discovery run produced the per-run cost number the scaling assessment
consumes), and Day 2 is now complete. Each block's Definition of Done is the repo standard (D-021): green gates
(ruff/format/mypy/import-linter/pytest, + frontend eslint/tsc/vitest where the change touches `frontend/`) +
a human-read diff + updated docs, on a branch → PR.

---

## Day 1 — UI rework ✅ (D-080; plan of record: `docs/16-ui-rework-plan.md`)

**Done — all 4 PRs merged (#74–77) and live in prod (verified on `main` 2026-07-13).** Scoped 2026-07-12 in
a planning session (every decision Hayden's). The timeboxed reference-pick resolved to
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

## Day 2 — Discovery agent: live run + supporting tooling ✅ (D-084)

**Done; operation is deliberately manual/on-demand.** Multiple complete GPT-5.6 Terra runs exercised all
three research waves plus ATS resolution on both verticals. Complete-run estimates were approximately
**$0.77–$0.99 per run**; the reports/checkpoints live in `data/discovery_reports/`. The coverage ledger exists
in `docs/07`, the 2026-07-12 coverage audit supplied the low-signal retire slate, and `vja-review` supplies the
human correction/approval path. Hayden does **not** want a scheduled discovery Job: run `vja-discover` only
when the company universe needs a refresh. This supersedes the old "measure cost, then decide whether to turn
the weekly schedule ON" framing (D-071); there is no remaining schedule-enable gate.

The original execution brief is retained below as history; its live-run and measurement requirements are met.

- **Scope:**
  - Run the live `vja-discover --vertical <vertical>` loop when needed (needs `OPENAI_API_KEY` + web search;
    Hayden-run) → review/approve via `vja-review`. Operator guide: `docs/14`.
  - **Coverage ledger** — a way to see fetchable vs. parked vs. proposed across the universe, so "how much do
    we actually cover" is a number, not a guess.
  - **Low-signal pruning** — drop/retire noisy or irrelevant employers the run surfaces (the agent adding
    companies is exactly when noise creeps in).
- **Produces:** the **real per-run cost** of discovery and the LLM-spend input Day 4 needs.
- **DoD met:** complete live runs + reports; coverage ledger; measured cost; correction/review tooling with
  tests. Proposal activation/retirement continues as ordinary company-database curation, not as unfinished
  discovery-agent implementation.

**First live run — 2026-07-10 (partial):** after fixing a self-starving tool budget (searches/fetches 8→20/16,
`$` ceiling 2→4; the old per-request `max_uses`==cumulative-cap coupling ended the run after one blocked turn —
see WORKLOG) the loop did **real oblique sourcing**: 5 candidates off the Energy Impact Partners portfolio
(GridBeyond, GridX, Emerald AI, CivilGrid, eSmart Systems), all landing `proposed`/`layer2` (GridBeyond's ATS
confirmed **BambooHR** — the fetcher is now built, with activation pending deployment + D-077 review;
the other four are JS-rendered/unresolved). **New binding
constraint at the time:** the run stopped on an **external web-tool rate limit (429s), not our `$`/tool caps**
and completed only ~1 of ~3 planned source waves. D-074's move to Terra replaced that provider/tool loop;
later complete runs supplied the missing cost/yield evidence. Triage and activation are now ordinary
company-database work.

**Provider/ATS hardening branch — 2026-07-10:** the next run moves discovery only to GPT-5.6 Terra
(D-074). It replaces the single Claude loop with three independently capped source waves and reserves a
separate four-action resolver for each of at most five candidates. Canonical provider-URL evidence plus
the existing validate-by-fetch gate is required before a supported ATS is stamped; confirmed unsupported
providers and typed failure reasons remain visible in proposal notes. The complete Terra runs supplied the
cost/yield evidence; D-084 closes the schedule question as manual-only.

## Day 3 — Bug shakeout (+ onboarding overhaul — ACTIVE, D-082/D-085; plan: `docs/17-onboarding-plan.md`)

Fix bugs surfaced by real private-user usage and the Day-2 run. Bug fixes **start with a failing regression
test** (D-021).

- **Onboarding overhaul (scoped 2026-07-13, D-082):** the first real user's fresh-signup walkthrough exposed
  the untested onboarding path — the "stuck on upload page" bug cluster, the reupload match-orphaning UX gap,
  no matching-progress signal, no `/upload` back nav, ambiguous toggles, no tutorial. A **3-PR block** (see
  `docs/17`): PR 1 upload/onboarding bug fixes → PR 2 backend backfill-status signal (+migration) → PR 3
  welcome-slides tutorial + toggle clarity. **PR 1 merged #78; PR 2 merged #79; its production
  schema/auth follow-up merged #80 (D-083); PR 3 merged #82.** PR 3 adds the four-slide
  first-run/reopenable tutorial, clarifies both toggle groups,
  moves the table-use hint above the results, and displays `aviation_software` as **Aviation Technology**
  without changing the internal slug. Frontend gate: 95/95 + 1440/720 visual pass.
- **Scope:** whatever real usage exposes — onboarding edge cases, digest content, dashboard windows, fetcher
  drift.
- **Accepted sub-item (D-085):** **basic observability/alerting on the nightly** so a
  silent failure doesn't strand private users who now depend on the digest. `docs/11` deferred this; the
  minimum is "if the nightly fails or sends nothing unexpectedly, Hayden finds out." Small, but it's the
  difference between "beta" and "beta that embarrasses you."
- **2026-07-14 retry/duplicate incident guard (D-086):** one long execution sent aviation, hit the
  old 2-hour task timeout during grid, and Cloud Run's one automatic retry reran the whole command,
  sending aviation twice before grid completed. Immediate guard: **6-hour timeout + zero automatic
  retries**, reasserted by `ship.sh` and test-pinned. Durable per-execution digest idempotency remains
  follow-up work alongside minimum Job monitoring.
- **DoD:** a regression test per fix; green gates; WORKLOG notes each bug + fix.

**Accepted follow-up queue (D-085; separate reviewable PRs after onboarding PR 3):**

1. **Landing copy de-duplication ✅ (merged #86):** outward
   *software/engineering → technology* language; cards = benefits, How it works = mechanics, founder story =
   Hayden's recruiting problem and thesis. The Robotics promise remains by Hayden's explicit choice; its
   config is still a separate beta-exit item.
2. **Résumé-reupload abuse guard ✅ (merged #87):** identical extracted content keeps the 202 contract
   without a progress-stamp refresh or backfill; changed content is limited to one accepted reupload per
   user per rolling 24 hours through an atomic user-row clock (server-side 429 + integer-seconds
   `Retry-After`). **Neon migration
   `c4e8a7d9132f` applied and verified 2026-07-15.**
3. **Snapshot-integrity churn guard ✅ (merged #88, D-088):** stable
   44-employer runs on July 8–10 still reported 343–654 new and 384–592 closed postings. The code
   audit found a concrete completeness gap: five paginated providers trusted only the first total,
   accepted over-counts, and the shared sync silently collapsed duplicate external IDs before
   diffing. Paginated totals are now stable+exact, and duplicate IDs fail before any DB mutation;
   changed/failed employer outcomes are logged for attribution. This closes the known vulnerability,
   not the entire causal diagnosis. The July 16 run started before #88 merged, so it is a pre-fix
   baseline. The July 17 audit confirmed NextEra's large new/reopened count was the corrected Radancy
   snapshot catching the DB up, but also found **14 Workday tenants failing `nonzero → 0` on page two**.
   PR #92 merged July 20, so July 21 was the first actual D-091 evidence run: all 15 affected boards' zero-total
   pages were complete/disjoint against page one's target, with no overlap or malformed IDs. **D-092 correction
   built:** accept consistent repeated-total or zero-sentinel modes while preserving exact/unique fail-closed
   guards; Airbus/Thales remain failed closed on the ambiguous 2,000/full-page cap signature. The noisy shadow
   walk is retired. Post-deploy scheduled observation remains; no manual duplicate board fetch.
   *(This item gates intraday freshness/alerts and lifespan intel; see `docs/18`, D-087.)*
4. **Match-score boundary guard ✅ (D-089, built on `fix/match-score-boundary`):** the July 16
   shakeout found 26 otherwise-valid match results discarded for negative scores, with 56 occurrences
   across seven execution dates. Integers outside 0–100 now clamp to the nearest boundary and log;
   malformed/non-integer results still fail, and no paid corrective retry is added.
5. Minimum cloud observability: alert when the scheduled nightly does not start/fails at the platform level,
   and make partial coverage degradation + LLM-spend trends visible. The existing in-process hard-failure and
   digest-send email remains useful but cannot alert if the Job never starts.

## Day 4 — Scaling plan (analysis + guardrails)

A written scaling assessment across every external dependency, **now including Anthropic/LLM spend as a fifth
pillar** (Hayden's call — folded in rather than a separate day).

- **Five pillars:**
  1. **Neon** (Postgres) — connection limits, autosuspend behavior, storage/compute tier, backups.
  2. **GCP / Cloud Run** — service + Job scaling, concurrency, cold starts, cost at N users.
  3. **Resend / deliverability** — sending volume limits, domain reputation, bounce handling on the verified
     `role-feed.com` sender.
  4. **Google OAuth** — consent-screen/verification status, user cap, quota.
  5. **Provider-neutral LLM spend** — read the **real nightly token numbers** now persisted to `pipeline_runs`
     (D-069's four token columns). **D-085 sequencing:** first explain/fix the abnormal new/closed identity
     churn; D-088 lands the conservative snapshot-integrity fix and adds the attribution logs. **Message
     Batches are deferred** because a batch may take up to 24 hours and postings are time-sensitive. Observe
     two production nights and re-measure steady state; if extraction remains material, reconsider
     **extraction batching first** (input-bound and uncacheable). Matching already showed roughly 84–93%
     cache hits on most measured nights and is not the first target. Set spend guardrails beyond the
     existing backfill cap + daily ceiling (D-057, D-088).
- **Accepted pre-beta/Robotics optimization program (D-090/D-093, `docs/19`):** extraction retained Haiku;
  the human-reviewed eight-case matching decision selected GPT-5.6 Luna low over Sonnet medium. Both live-model
  evals stay manual evidence, not paid CI gates. Build no generic benchmark or `no`-output follow-on; provider
  dashboards are authoritative for cost.
- **DoD:** a written scaling doc (thresholds + "what breaks first" + the Block-2 decision); any guardrail
  config that's cheap to land now. Reads `docs/11` (portability ledger) as the baseline.

## Day 5 — More fetchers / company-database expansion (ONGOING, not a beta-exit gate)

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

**D-085 focus after onboarding:** continued UI/UX iteration, building the employer/company databases, and
incorporating beta-user feedback are the main product loops. Execute already-validated no-code activations;
then add fetchers by the `docs/07` demand ledger when coverage demand justifies them. An endless fetcher queue
does not block broader beta by itself.

## Beta exit line (accepted 2026-07-13, D-085; **reduced 2026-07-22, D-094**)

- Onboarding PR 3 merged #82; landing copy merged #86; the reupload guard merged #87. ✅
- Robotics promise mismatch resolved: the vertical config merged #93 and its Neon baseline ran. ✅
- D-090/D-093 matching decision complete: Luna low merged #97 and deployed. ✅
- **Compliance/usability block (D-094, 3 PRs):** privacy notice (PR 1, merged #99) → digest
  unsubscribe (PR 2, merged #100: `users.digest_paused` + tokenized confirm-page/POST `/unsubscribe` +
  RFC-8058 one-click headers + paused skip in `send_digest`) → settings + account deletion
  (PR 3 — **built**: `/settings` page with the pause/resume toggle over `PATCH /api/me` + hard
  deletion via `DELETE /api/me` — user/profiles/matches/digest rows in one transaction,
  postings/employers untouched; no migration).
- **Kept minimums (D-094):** one GCP alert-policy pair on the nightly Job (failed / did-not-run);
  one-time Google OAuth publishing-status check (the 100-user "Testing" cap); the July-23 read-only
  first-Luna-night audit; the already-validated no-code employer activations (Hayden-run, not a gate).
- **Dropped (D-094):** the five-pillar written scaling assessment, D-086's durable digest delivery
  idempotency (the 6h/zero-retry guard covers the observed path), and monitoring beyond the single
  alert pair.

Scheduled discovery and the remaining generic-fetcher roadmap are explicitly outside this exit gate.

**What comes after the exit:** the post-beta feature roadmap lives in `docs/18-post-beta-features.md`
(D-087) — intraday freshness + alerts, salary display, recurring-gaps report, lifespan intel.

---

## Not in this week's scope (parked, tracked)

- **Auto-approval + proposal-precision eval** for discovery (Phase 10 later — needs a real sample).
- **Non-employer `sources`** (HN/niche) discovery.
- **A scheduled discovery Job** — explicitly not planned; discovery is manual/on-demand (D-084).
- **Moving `config/verticals/*.yaml` out of the image** (Path-A config) — premature per `docs/11` §5; revisit
  when Path-B redeploys actually hurt.
