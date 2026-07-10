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

## Day 1 — UI rework

Real landing page + dashboard polish, modeled on a proven industry-leader UX (copy what works rather than
invent). **Timebox the "which leader / what to copy" decision** up front (~30 min) so reference-hunting
doesn't eat the build day.

- **Scope:** `frontend/` — `Landing` page overhaul, login/dashboard visual polish. No backend contract change
  (the `/api/me` + `/api/postings` shapes stay put; this is presentation).
- **DoD:** frontend gate (eslint + `tsc --noEmit` + vitest) green; human-read diff; screenshots of before/after
  in the PR.
- **Watch:** keep the Rolefeed brand; don't regress the D-065 route guards (`/` smart-root, `/onboarding`,
  `/dashboard`, `/upload`). One vertical per user (D-064) is a policy, not a UI toggle — don't reintroduce a
  cross-user vertical picker.

## Day 2 — Discovery agent: live run + supporting tooling

Run `vja-discover` → `vja-review` for real (the still-pending 10.1/10.2 live smoke folds in here), landing a
good batch of new companies with **minimal manual input**. This is where the ready-but-OFF weekly schedule
earns its enable decision.

- **Scope:**
  - Run the live `vja-discover --vertical grid_power_software` loop (needs `ANTHROPIC_API_KEY` + web search;
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
confirmed **BambooHR** — not yet a supported fetcher; the other four JS-rendered/unresolved). **New binding
constraint (feeds Day 4):** the run stopped on an **external web-tool rate limit (429s), not our `$`/tool caps** —
so discovery *yield* is now gated by the Anthropic `web_search`/`web_fetch` rate limit, not our budget. It
completed only ~1 of ~3 planned source waves. Before flipping the weekly schedule ON, decide whether that limit
is per-minute (→ add pacing/backoff between waves) or a hard quota. Triage of #91–95 + the BambooHR-fetcher
question are still open.

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

Expand coverage. **Phenom next** (D-052) — the `/widgets/` JSON API behind the airline portals
(United/Southwest), the largest remaining coverage win. Then singletons / the Layer-2 tail as time allows.

- **Scope:** one generic Phenom platform fetcher (D-017 — no per-company scrapers), config-only onboarding of
  the tenants it unlocks. Parity with the list-only fetchers where applicable (`extract._DETAIL_RESOLVERS`).
- **DoD:** fetcher + tests (fixtures, not live) green; employers onboarded config-only; coverage count updated
  in the ledger + CLAUDE.md Phase 8 line.

---

## Not in this week's scope (parked, tracked)

- **Auto-approval + proposal-precision eval** for discovery (Phase 10 later — needs a real sample).
- **Non-employer `sources`** (HN/niche) discovery.
- **Enabling the weekly discovery schedule** — gated on Day 2's measured cost; flip is config, not code (D-031).
- **Moving `config/verticals/*.yaml` out of the image** (Path-A config) — premature per `docs/11` §5; revisit
  when Path-B redeploys actually hurt.
