# Vertical Job Intelligence Agent

## What this project is

A vertical job intelligence agent: a scheduled pipeline that achieves total coverage
of a small, bounded employer universe (~40 companies per vertical), diffs postings
daily, and delivers a digest of new/closed roles with LLM-written match rationale
against the user's resume. NOT a live chat agent. NOT a horizontal job board.

Launch verticals (both planned day one; **grid/power is built first** — it's the seeded/verified one. Aviation is
the Week-4 architecture-test add. See Build sequence + D-022):
1. **Aviation software** — airline ops/tech arms (United, Delta, JetBlue, Southwest,
   Alaska), platforms (Sabre, Amadeus, Navitaire), data/tracking (FlightAware,
   Cirium, Flightradar24), startups (FLYR, Volantio). Scope: early-career
   software/data roles, US.
2. **Grid/power software** — ISOs/RTOs (ERCOT, CAISO, PJM hire engineers directly),
   grid software (Camus, GridStatus, Arcadia), storage/DER (Tesla Energy, Fluence),
   power trading/analytics, nuclear revival, utility innovation arms.
   Deliberately NOT broad "climate tech" (Climatebase owns that).

Builder (Hayden) is the first user — actively recruiting into both verticals.

## Architecture (three layers — cheap deterministic path always tried first)

1. **Layer 1 — ATS spine.** Deterministic fetchers against public ATS JSON endpoints:
   - Greenhouse: `boards-api.greenhouse.io/v1/boards/{company}/jobs`
   - Lever: `api.lever.co/v0/postings/{company}`
   - Ashby: similar public posting endpoint
   - Workday (airlines, utilities): JS-heavy; mimic internal JSON API calls;
     treat as high-maintenance with per-company config + loud failure alerts.
2. **Layer 2 — LLM retrieval/extraction.** Unstructured sources: raw-HTML careers
   pages (LLM-read-the-page as universal fallback), HN Who's Hiring, niche boards.
   Only runs on items the Layer 1 diff flags as new/changed.
3. **Layer 3 — agentic discovery (manual/on-demand).** Agent finds new EMPLOYERS, not
   postings: VC portfolios, conference sponsor lists, funding news. Writes
   proposed employer records into a review queue (human approval at first).

## Execution model (decided)

- ALL fetching, API keys, and LLM calls run server-side in the nightly pipeline.
  Users only read precomputed results from the DB. Each ATS endpoint is hit once
  per day TOTAL regardless of user count.
- Pipeline order: fetch → diff → extract → match → verify → send digests.
- **Matching is push, not pull**: nightly batch keyed on (new posting, active
  resume) pairs. **Two cheap gates precede the strong model (D-023):** a free
  Layer-1 scope gate on the title (in-scope role/geo/level at all — drops
  out-of-scope postings before any LLM cost), then a cheap level/location/work-auth
  pre-filter that decides which survivors earn the rationale model.
- On-demand matching path reserved for exactly three cases: new-user backfill
  (match resume vs all open postings at signup), resume updates (re-match;
  store resume_version per match), and per-posting deep-dive (later, paid tier).

## Hard design rules

- **Nothing vertical-specific in code.** A vertical = config: employer list
  (ATS type + endpoint), niche sources, matching profile (resume + domain
  vocabulary). Adding vertical #2 must cost only curation + config.
- **The diff is the product.** Never show stale listing walls; show what changed.
  Mark vanished postings closed (never delete) — death detection keeps dead links
  out of the digest and yields posting-lifespan stats per company.
- **Matching is reasoning, not similarity.** Every rationale must state: what fits,
  what does NOT fit, and a verdict. Willingness to say no is a product requirement.
- **Verification before digest.** Every apply link must resolve before a posting
  ships. One fake posting costs more trust than ten real ones earn.
- **Cost discipline**: cache extraction by content hash; model tiering (cheap model
  for extraction, strongest for match rationale); LLM only where structure runs out.
  Meter LLM spend from day one.
- **No auto-apply.** The tool surfaces and reasons; it never submits applications.

## Data model (five core entities)

- `employers` (vertical, name, ats_type, endpoint/careers_url, source
  [manual|agent_discovered], status [proposed|approved|active|retired],
  early_career_volume_estimate)
- `sources` (non-employer feeds, e.g. HN thread, typed by ingestion method)
- `postings` (employer/source ref, raw payload, content_hash, first_seen,
  last_seen, status [open|closed], extracted fields: title, level, location,
  remote, visa/work-auth, stack, comp, apply_url)
- `matches` (posting, profile, score, written rationale, verdict, model_version,
  resume_version, trigger [nightly|backfill|refresh])
- `digests` (what was sent, when, contents — system behavior is auditable)

Diff identity is the ATS `external_id`, never fuzzy title/company/location matching. A duplicate
`external_id` inside one employer snapshot fails the snapshot before any DB mutation; it is never
silently collapsed or LLM-adjudicated. (D-016, D-088)

## Stack

Python pipeline, FastAPI (serves the dashboard's read-only API), SQLite → Postgres
migration path, embedded LiteLLM behind the typed `vja.llm` boundary for Layer-2 model calls
(Anthropic defaults today), direct OpenAI SDK for discovery, APScheduler or cron, React
dashboard.

## Delivery surfaces (decided)

- **Email digest = push** (primary). New postings + match rationale + closures,
  sent at the end of the nightly pipeline. Postings are time-sensitive; output
  must arrive whether or not the user remembers the tool exists.
- **Dashboard = pull** (read-only). A single-page React table over the same
  nightly-computed data: title, company, apply link, match quality (verdict/score),
  default sort newest-first. Updates once daily with the pipeline — no live fetching,
  just a window onto the DB. **v1 includes recency toggles** — *new today* / *updated
  within a week* / *within two weeks* / *all open* — over the full open set; this is the
  feature that justifies the pull surface beside the push digest (D-030). Windows key on
  the ATS posted/updated date (posted **or** updated within the window; D-024); *new
  today* uses `first_seen_at` so it equals the digest. Further polish is post-week-4.

## Build sequence (phase roadmap)

Terminology: a **Phase** is a themed milestone; a **Block** is one reviewable PR-sized unit inside a phase
(earlier work called these "chunks" — same thing). Grid/power (energy) is the first-built vertical (D-022).
Order revised by **D-026** (Workday moved up ahead of Layer 2 + dashboard — it's the biggest coverage win and the
high-volume meaningful jobs live there; it's pure Layer 1 and independent of matching).

- **Phase 0 — Docs/prep.** ✅ Specs, decisions, seed.
- **Phase 1 — Core logic & scaffolding.** ✅ models, `content_hash`, GH/Lever/Ashby fetchers, diff arithmetic.
- **Phase 2 — Persistence + Layer-1 implementation.** DB foundation + employer import ✅; fetch→diff→persist ✅;
  orchestration loop + `pipeline_runs` (in progress).
- **Phase 3 — Bare digest (proof of loop).** ✅ Assemble what changed → verify apply links (D-008) → email via Resend
  → schedule via launchd (`vja-nightly`, D-031). NO LLM. **First diff in the inbox = proof-of-loop milestone** (hit).
- **Phase 4 — Workday fetcher.** One generic `cxs` fetcher + per-tenant config → coverage ~9→24 of 54 (D-026/D-018).
  Pure Layer 1; rides on Phase 2's failure isolation + Phase 3's verification gate. **4.1 ✅** (12 verified tenants →
  21 fetchable; D-032, list-only + paginate-or-fail). **4.2 ✅** (GE Vernova + BP + Fluence onboarded from config →
  **24 fetchable**; `osv-` Workday hosts route to Layer 2). 4.3 = generic mass-closure guard.
- **Phase 5 — Layer 2: extraction + matching.** Profiles (resume), LLM extraction (cached by `content_hash`),
  two-stage filter (D-023), matching with fits/gaps/verdict (D-007) + eval gate (D-020); digest gains rationale.
- **Phase 6 — Dashboard.** Read-only FastAPI API + React table (title/company/apply/match) with **recency toggles**
  (new today / 1wk / 2wk / all open) over the full open set (D-030). Consumes the normalized ATS posted/updated date
  built for the Phase-5 backfill (D-024) — no new backend date work, so nothing reorders. **A1–B1 ✅** (date infra →
  recency query + backfill → read API, D-041). **B2 ✅** — the Vite/React/TS SPA in `frontend/` over `/api/postings`
  (in-scope/matched-default, the two match-status toggles + expandable rationale; D-042). Frontend gate = eslint +
  tsc + vitest (CI + pre-commit).
- **Phase 7 — Aviation vertical.** The architecture test — config + curation only, **any forced code change is a defect** (D-004).
- **Phase 8 — Remaining coverage.** Tier-B fetchers (iCIMS/Workable/Oracle/SmartRecruiters), then Layer-2 LLM-read
  for the custom tail + HN/niche sources. *(Likely opens new doors/decisions — kept first because more coverage
  makes the user-facing launch worth more.)* **iCIMS ✅** (D-048) — via the iCIMS **Career Sites (Jibe)**
  `{careers_base}/api/jobs` JSON API (one generic fetcher; legacy portal → Layer 2); +6 fetchable (incl. Garmin).
  Sabre + Amadeus also onboarded to Workday (config-only) → coverage **31→39**. **Workable ✅** (D-049) —
  via the embed-widget API `apply.workable.com/api/v1/widget/accounts/{slug}?details=true` (slug-derived,
  single-response); +2 fetchable (Vortexa, Energy Aspects) → **39→41**. **SmartRecruiters ✅** (D-050) —
  via the public postings API (slug-derived; list-only + paginate-or-fail + lazy detail, Workday parity);
  +1 (Vitol) → **41→42**. **Oracle HCM/ORC ✅** (D-051) — via the Candidate-Experience REST API
  (explicit per-tenant endpoint; list-only + lazy detail); +1 (Southern Company) → **42→43** (Honeywell +
  Con Edison hosts not found → Layer 2, onboard config-only when curated). The list-only ATSs' lazy detail
  is now routed by a per-ATS `extract._DETAIL_RESOLVERS` map
  (Workday/SmartRecruiters/Oracle/Radancy/Paylocity/Phenom/BambooHR).
  **Radancy/TalentBrew ✅** (D-052) — a Step-0 probe found the `custom`/`layer2` tail is mostly JS/bot-blocked,
  so the literal "LLM-read-the-page" step has near-zero reach; **decision: probe the multi-tenant platforms
  (Phenom, Radancy) for a clean API first** (the iCIMS lesson), deferring the generic LLM-read to the genuinely
  structureless remainder. Radancy = one generic **HTML-parse** fetcher (`beautifulsoup4`, the repo's first)
  over the server-rendered `{endpoint}/search-jobs/results` table (list-only + paginate-or-fail + lazy detail);
  `external_id` = the `/job/{slug}/{id}` path (Workday parity); +1 (NextEra) → **43→44** (NRG/National Grid/
  L3Harris parked `proposed` until their search base verifies). **SWA + Thales Workday config onboards ✅**
  (D-076; live-verified 2026-07-11; discovery-expanded production coverage **64 → 66**). **Paylocity ✅**
  (D-076/D-077) → **Phenom + United ✅** (D-076; config-driven) → **BambooHR ✅** → **Honeywell Oracle
  config onboard ✅** (D-078 coverage audit, 2026-07-12; canonical host found, 1,455 postings validated;
  activates at the next seed import). **Pinpoint ✅** (D-079; Aurora seed onboarded; Aireon pending D-077
  activation). **SPAN + The Brattle Group curated seed onboard ✅** (2026-07-14; Ashby + Greenhouse,
  **49 → 51 seed-fetchable**; production activates at the next seed import). **Next (D-078 re-rank):**
  no-code runbook activations (6 validated discovery rows) →
  Radancy variants (L3Harris JSON / NRG / AA) → JazzHR → Jobvite → Taleo,
  then the Layer-2 LLM-read tail for what truly has no platform (demand ledger: `docs/07`).
- **Phase 9 — Cloud migration + full product frontend (resequenced up; D-047).** The D-025 hosting/Postgres cutover
  (VPS + `VJA_DATABASE_URL` swap + `alembic upgrade`) **plus** the multi-user product surface: auth/login, resume
  upload (the D-033 adapter), vertical toggle, signup → backfill. Pulled ahead of the discovery agent to get real
  users in front of it. The deferred-work ledger in `docs/11` is this phase's checklist (auth, PII, abuse/cost
  guards, deliverability, observability). *(Was "cross-cutting, triggered by demo users.")* Block order: **9.1
  Postgres-CI spine ✅** (D-054) · **9.2 auth — Google OAuth + `users` + read-API authz ✅** (D-055) · **9.3 résumé
  upload + signup→backfill + cost guards ✅** (D-057 — `POST /api/profiles` behind `require_user`, `pypdf` adapter,
  background backfill, per-backfill cap + daily ceiling) · **9.4 multi-user frontend ✅** (D-058 — the
  **Rolefeed**-branded SPA: `react-router-dom` routes `/`·`/login`·`/upload`, Google-OAuth login chrome,
  credentialed fetches → own-profile resolution, résumé-upload form over `POST /api/profiles` with optimistic
  backfill UX; `VJA_AUTH_REQUIRED` stays off till 9.5) · 9.5 cloud deploy + full Postgres cutover + verified
  email domain + security review (+ flip `VJA_AUTH_REQUIRED` on, prod redirect URIs/cookie hardening, SPA
  deep-link catch-all). **Plan of record: `docs/12-cloud-deploy-plan.md`** — four sub-blocks **9.5a app
  hardening** (code) · **9.5b containerization** (code) · **9.5c provision** (GCP+Neon+domain) · **9.5d
  cutover/go-live**; locked: Neon (not Cloud SQL), Cloud Run, a `.com` via Cloudflare, fresh DB + suppressed
  baseline run. **9.5a–d ✅ — go-live infra done + closeout complete (D-067):** live on `role-feed.com`,
  Postgres/Neon, auth ON, nightly Job+Scheduler running, digests from the verified `digest@role-feed.com`
  (email E2E ✅), `/security-review` ✅.
- **Phase 9.x — onboarding overhaul + thin ship-script (`docs/13`).** The deployed onboarding/dashboard flow was
  broken for a fresh account — it treated vertical as a **global** picker, violating the standing
  **one-vertical-per-user** policy (D-064), so users 404'd. **Phase A ✅** thin scripted deploy (`deploy/gcp/ship.sh`;
  D-066) · **Phase B ✅** onboarding overhaul (D-065: static landing → Google auth → pick-vertical+upload → their
  dashboard; `/api/me`, route guards, one-vertical enforcement; PR #52). **✅ Done — beta invites unblocked:** B-4
  prod data cleanup + fresh-account walkthrough passed; **real private users are signed up and working.**
- **Phase 9.6 — full CI/CD ✅ (D-068).** Merge-to-`main` auto-deploys to Cloud Run (keyless WIF, smoke +
  auto-rollback; migrations stay manual), replacing the manual Phase-A `ship.sh` (which stays the break-glass).
- **Phase BH — beta hardening (ACTIVE; `docs/15`, scope D-072/D-085).** The pre-broad-invite workstreams —
  UI rework (**✅ done, D-080** → `docs/16`: Linear reference, design-language v2, a 4-PR block —
  foundation → landing → auth pages → dashboard; frontend-only, **all 4 PRs merged #74–77, live in
  prod**) · **onboarding overhaul (D-082/D-085 → `docs/17`: PR 1 upload fixes #78 ✅ → PR 2
  backfill status #79 ✅ → D-083 hotfix #80 ✅ → PR 3 welcome tutorial + toggle clarity #82 ✅ →
  D-085 landing-copy follow-up merged #86 ✅ → résumé-reupload abuse guard merged #87 ✅)** ·
  discovery-agent live run/ledger/pruning **✅ (D-084; manual/on-demand permanently, no scheduled Job)** ·
  nightly timeout/retry duplicate guard **✅ (D-086; 6h, zero automatic task retries)** · bug shakeout
  (**D-089 match-score boundary guard built ✅ — clamp/log integer outliers, no paid retry**) ·
  scaling plan (Neon/GCP/Resend/OAuth **+ Anthropic LLM spend**; D-088 snapshot-integrity churn
  guard merged #88 ✅, observe July 17–18 production nights; Message Batches deferred for freshness) · more
  fetchers/company-database growth
  (demand-ranked, D-076: SWA/Thales Workday configs ✅ → Paylocity + D-077 `vja-review set-ats` tooling ✅ →
  Phenom/United ✅ → BambooHR ✅ → **2026-07-12 coverage audit + Honeywell Oracle onboard ✅ → Pinpoint ✅
  (D-079), next order = D-078**: runbook activations → Radancy variants → JazzHR → Jobvite → Taleo).
  **Beta exit:** PR 3 + user-facing fixes/reupload guard + robotics-promise resolution + minimum Job monitoring +
  scaling assessment + validated no-code activations. After that, the main loops are UI/UX, company databases,
  and beta-user feedback; scheduled discovery and the endless fetcher tail are not exit gates (D-085).
- **Phase 10 — Layer 3: discovery agent (resequenced down; D-047/D-084).** On-demand agent finds new *employers* →
  `proposed` rows in a review queue. A nice-to-have, not essential: shell + formatting around Opus deep web search
  → new companies into the DB. Deferred because it doesn't gate a user-facing launch. **10.1 thin core ✅** (D-070):
  `vja-discover` — **GPT-5.6 Terra** three-wave web research → budgeted per-candidate **ATS
  resolution** → **validate-by-fetch** →
  `proposed`+`agent_discovered` rows (fetchable→`detected`, else `unknown`/`layer2`); metered + bounded; no
  migration (schema already had the enum values, only `active` is fetched). **Cost-hardened
  (D-073/D-074):** requests are prompt-cached, independently tool-capped, included in the `$4`
  token+search-fee meter, and checkpointed incrementally. The ATS resolver requires canonical
  provider-URL evidence; only a successful registry fetch stamps a supported ATS.
  **10.2 ✅** (D-071): the `vja-review` approve/reject/list CLI — the human gate
  that promotes proposals (`approve`→`active` if fetchable, else `approved`+parked; `reject`→`retired`; fetchability
  keyed on `SUPPORTED_ATS_TYPES`, parked rows structurally unfetchable). **Live-run gate ✅ (D-084):** complete
  Terra runs measured ~$0.77–$0.99; discovery is **manual/on-demand by policy**, with no recurring schedule
  planned (disabled templates remain available machinery). **Later:** auto-approval, a proposal-precision eval,
  and non-employer `sources`.
- **Post-beta feature slate (planned; D-087, `docs/18`).** Decided 2026-07-14, builds only after the D-085
  beta exit: intraday freshness + instant alerts (supersedes D-005's once-daily fetch at build time) ·
  salary display (own extraction first, then DOL H1B/LCA enrichment; Glassdoor/Indeed path closed) ·
  recurring-gaps report · per-employer lifespan/urgency intel. The D-085 churn diagnosis blocks the
  freshness + lifespan builds.

## Conventions for this repo

- Politeness is policy: rate limits, sane user agent, respect robots.txt on the
  long tail. Getting IP-banned is a self-inflicted coverage hole.
- Per-fetcher health checks with loud alerts; every pipeline run writes a
  summary record. A digest that fails to send is itself an alert.
- API keys in env config, never in the repo. DB never publicly exposed. Application CLIs auto-load
  a git-ignored `.env` (python-dotenv); **Alembic does not**, so migrations require an explicit
  `VJA_DATABASE_URL` export (D-083). Layer-2 routes = `VJA_EXTRACT_MODEL` (default
  `anthropic/claude-haiku-4-5`) + `VJA_MATCH_MODEL` (default `anthropic/claude-sonnet-4-6`), through
  embedded LiteLLM; provider/send config = `RESEND_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `VJA_DIGEST_FROM`
  (default sandbox `onboarding@resend.dev`), and `VJA_DIGEST_RECIPIENT` — which as of P5.4 is the
  **ops/alert** recipient (failure alerts); the *digest* recipient is the matched profile's
  `user_email` (D-027/D-037). Nightly job = **`vja-nightly`** (composes run → extract → match → digest
  per profile, alerts on hard failure), scheduled via launchd (`deploy/launchd/`); `vja-run`/`vja-extract`/
  `vja-match`/`vja-digest` remain as separate debugging entry points. Scheduler is a swappable trigger —
  cloud cutover swaps it, not code (D-031).
- **Testing is policy, not preference (this code is model-written).** No behavior is "done" until a test pins it at
  the right level; bug fixes start with a failing regression test. Default `pytest` (unit+integration+system) stays
  fast/offline/free; `live`/`eval`/`e2e` are opt-in markers. Full rules: `docs/08-testing-strategy.md`.
- **Definition of Done + gates:** green tests + lint/format/types + a human-read diff + updated docs, before merge.
  See `docs/09-dev-workflow.md`.
- See `docs/` for full planning context: business concept, technical write-up,
  and open-questions ledger.

## Documentation discipline (strict — this project documents as it builds)

- **Every working session updates `WORKLOG.md`** (append-only, newest on top): what changed, why,
  what's next, open threads. It is the narrative backup to git history.
- **Every decision that could be re-litigated lands in `DECISIONS.md`** as a short ADR
  (id · date · decision · why · status). Supersede rather than delete.
- **When an ADR changes a live cross-cutting rule, update `docs/INVARIANTS.md` in the same
  session** — replace the affected line, don't append. ADRs are the log; INVARIANTS is the
  current head. They drifting apart is the failure mode this guards against.
- **Specs live in `docs/`**, numbered. Build-spec docs (`04+`) are the source of truth for the
  schema/interfaces and override the prose sketches in the 01–03 memos where they differ.
- **Seed/config is documented next to the data** (`data/seed/README.md`, `config/verticals/*.yaml`).
- Order of authority when docs disagree: build specs (`docs/04+`) > CLAUDE.md > planning memos (`docs/01–03`).

### Doc map
- `docs/INVARIANTS.md` — **read first.** The derived "what's true right now" registry of
  cross-cutting rules, each pointing to its backing ADR. The fast antidote to acting on a
  stale rule. The layering rule in it is machine-enforced by `import-linter`.
- `docs/01–03` — planning memos (business, technical, open questions). Context, not spec.
- `docs/04-data-model-spec.md` — concrete schema; the diff keys on `external_id`, not fuzzy match.
- `docs/05-fetcher-interface-spec.md` — the common Fetcher contract + per-ATS modules.
- `docs/06-vertical-config-spec.md` — "a vertical is config"; the Week-4 test.
- `docs/07-ats-routing.md` — ATS platform distribution + fetcher build priority (no per-company scrapers).
- `docs/08-testing-strategy.md` — the four test levels (unit→integration→system→e2e) in this project's terms + when each applies.
- `docs/09-dev-workflow.md` — Definition of Done, branch/PR/review gate, CI + pre-commit gates, conventions. The "Claude writes it, gates + review make it trustworthy" playbook.
- `docs/11-multi-user-and-hosting.md` — living migration ledger: what's already portable, the single-user seams each phase must preserve, and the deferred auth/security/PII/cost work to build at the D-025 cutover. §5 = post-launch change management (data-only vs config/code redeploy loops; drives the vertical-expansion + discovery-agent roadmap).
- `docs/12-cloud-deploy-plan.md` — Phase 9.5 plan of record (sub-blocks 9.5a–d + locked decisions). Read it + `docs/11` + the WORKLOG top entry to continue 9.5 after a chat reset.
- `docs/14-discovery-cli-guide.md` — operator guide for the Layer-3 discovery workflow: `vja-discover` + `vja-review` commands, which DB they write (local vs Neon/prod), cost, and the first-run walkthrough (D-070/D-071).
- `docs/15-beta-hardening-plan.md` — the active beta-hardening workstreams (UI · discovery run · bugs/onboarding · scaling incl. LLM spend · fetchers/company data), beta exit line, DoD per block, and what's parked. Scope of record: D-072/D-085. Read after `WORKLOG.md` top to continue.
- `docs/16-ui-rework-plan.md` — the Day-1 UI rework plan of record (D-080): Linear reference, design-language v2 direction, the 4 PRs (foundation → landing → auth → dashboard) with per-PR scope + DoD. All 4 merged (#74–77).
- `docs/17-onboarding-plan.md` — the onboarding-overhaul plan of record (D-082): the 3 PRs (upload-flow bug fixes → backfill-status signal + migration → welcome-slides tutorial + toggle clarity) with per-PR scope + DoD. Read to continue the overhaul after a chat reset.
- `docs/18-post-beta-features.md` — the post-beta feature roadmap (D-087): intraday freshness + instant alerts, salary display (own extraction → H1B/DOL enrichment), recurring-gaps report, lifespan/urgency intel — with sequencing, the churn-fix prerequisite, and the rejected-features record. Planning only; nothing live.
- `docs/19-llm-optimization-plan.md` — the pre-beta/Robotics LLM cost program (D-090): observe D-088 → LiteLLM provider boundary → multi-model eval/CI repair → extraction cutover → matching cutover → chosen-model `no`-output optimization.
- `DECISIONS.md` — decision log (D-001…). `WORKLOG.md` — session log.
- `data/seed/employers_seed.csv` (+ README) — the curated employer universe.

## Kill criterion (do not quietly forget)

If the builder stops reading his own digest by week three, the product hypothesis
is falsified. The project still wins as a portfolio piece and interview story.
