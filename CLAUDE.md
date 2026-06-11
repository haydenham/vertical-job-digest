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
- **Dashboard = pull** (simple, read-only). A single-page React table over the
  same nightly-computed data: title, company, apply link, match quality
  (verdict/score). Default sort: newest first. Updates once daily with the
  pipeline — no live fetching, no logic of its own, just a window onto the DB.
  Deliberately minimal in v1; polish is post-week-4.

## Build sequence

- **Weeks 1–2**: Layer 1 skeleton, **grid/power (energy) only** — this is the first-built vertical and the one
  already seeded/verified (D-022). Employer table,
  Greenhouse/Lever/Ashby fetchers, postings table, diff job, bare-bones daily
  email. NO LLM yet. First diff in inbox = proof-of-loop milestone.
- **Week 3**: LLM extraction + matching (incl. negative-case rationale +
  verification step). Minimal dashboard ships here: four-column table
  (title, company, apply link, match quality) — the match column requires
  the matching engine, hence the timing.
- **Week 4**: Add **aviation vertical**. This is the architecture test — must cost
  only a weekend of curation + a config file. Any forced code change is a defect.
- **After**: Workday fetchers, HN extraction, discovery agent, dashboard polish.

## Conventions for this repo

- Politeness is policy: rate limits, sane user agent, respect robots.txt on the
  long tail. Getting IP-banned is a self-inflicted coverage hole.
- Per-fetcher health checks with loud alerts; every pipeline run writes a
  summary record. A digest that fails to send is itself an alert.
- API keys in env config, never in the repo. DB never publicly exposed.
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
