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
3. **Layer 3 — agentic discovery (weekly, later).** Agent finds new EMPLOYERS, not
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

Dedup: fuzzy match on normalized title+company+location; LLM adjudicates
ambiguous pairs during extraction.

## Stack

Python pipeline, FastAPI (serves the dashboard's read-only API), SQLite → Postgres
migration path, Anthropic SDK for all model calls, APScheduler or cron, React
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
  built for the Phase-5 backfill (D-024) — no new backend date work, so nothing reorders.
- **Phase 7 — Aviation vertical.** The architecture test — config + curation only, **any forced code change is a defect** (D-004).
- **Phase 8 — Remaining coverage.** Tier-B fetchers (iCIMS/Workable/Oracle/SmartRecruiters), then Layer-2 LLM-read
  for the custom tail + HN/niche sources.
- **Phase 9 — Layer 3: discovery agent.** Weekly agent finds new *employers* → `proposed` rows in a review queue.
- **Cross-cutting — Hosting & Postgres cutover (D-025).** Triggered by demo users (~2 weeks): VPS + Postgres URL swap
  + `alembic upgrade`. Slot relative to Phases 3–5 per demo-readiness.

## Conventions for this repo

- Politeness is policy: rate limits, sane user agent, respect robots.txt on the
  long tail. Getting IP-banned is a self-inflicted coverage hole.
- Per-fetcher health checks with loud alerts; every pipeline run writes a
  summary record. A digest that fails to send is itself an alert.
- API keys in env config, never in the repo. DB never publicly exposed. A git-ignored `.env` is
  auto-loaded (python-dotenv); send config = `RESEND_API_KEY`, `ANTHROPIC_API_KEY`, `VJA_DIGEST_FROM`
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
- **Specs live in `docs/`**, numbered. Build-spec docs (`04+`) are the source of truth for the
  schema/interfaces and override the prose sketches in the 01–03 memos where they differ.
- **Seed/config is documented next to the data** (`data/seed/README.md`, `config/verticals/*.yaml`).
- Order of authority when docs disagree: build specs (`docs/04+`) > CLAUDE.md > planning memos (`docs/01–03`).

### Doc map
- `docs/01–03` — planning memos (business, technical, open questions). Context, not spec.
- `docs/04-data-model-spec.md` — concrete schema; the diff keys on `external_id`, not fuzzy match.
- `docs/05-fetcher-interface-spec.md` — the common Fetcher contract + per-ATS modules.
- `docs/06-vertical-config-spec.md` — "a vertical is config"; the Week-4 test.
- `docs/07-ats-routing.md` — ATS platform distribution + fetcher build priority (no per-company scrapers).
- `docs/08-testing-strategy.md` — the four test levels (unit→integration→system→e2e) in this project's terms + when each applies.
- `docs/09-dev-workflow.md` — Definition of Done, branch/PR/review gate, CI + pre-commit gates, conventions. The "Claude writes it, gates + review make it trustworthy" playbook.
- `DECISIONS.md` — decision log (D-001…). `WORKLOG.md` — session log.
- `data/seed/employers_seed.csv` (+ README) — the curated employer universe.

## Kill criterion (do not quietly forget)

If the builder stops reading his own digest by week three, the product hypothesis
is falsified. The project still wins as a portfolio piece and interview story.
