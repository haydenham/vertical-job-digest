# Decision Log

Lightweight ADRs. One entry per decision that would otherwise get re-litigated.
Format: **ID · date · decision · why · status**. Supersede rather than delete; mark the old one.

Status values: `accepted` (in force), `superseded` (replaced — link the replacement), `proposed` (not yet committed).

---

### D-001 · Scope: vertical, not horizontal · accepted
Total coverage of a small bounded employer universe (~40/vertical), not a horizontal board.
**Why:** the horizontal lane is contested by funded players; the vertical lane competes with nobody. (Memo 01)

### D-002 · Two launch verticals from day one: aviation software + grid/power software · accepted
**Why:** cheapest possible proof of the "vertical = config" expansion thesis; founder is the target user in both. (Memo 01)

### D-003 · Three-layer architecture, cheap deterministic path first · accepted
L1 ATS spine (deterministic JSON) → L2 LLM extraction (unstructured only, on diff-flagged items) → L3 weekly discovery agent.
**Why:** use LLM reasoning only where structure runs out; bound cost. (Memo 02, CLAUDE.md)

### D-004 · Nothing vertical-specific in code · accepted
A vertical is data: employer list + niche sources + matching profile. Adding a vertical must cost only curation + config.
**Why:** the whole expansion playbook depends on it; the week-4 **aviation** add is the test (energy is built first — D-022). (CLAUDE.md, Memo 02)

### D-005 · Server-side nightly pipeline; users only read precomputed results · accepted
All fetching/keys/LLM calls run in the nightly batch. Each ATS endpoint hit once/day total regardless of user count.
**Why:** spend scales with postings/day, not user activity. (Memo 02 §9)

### D-006 · Matching is push (nightly batch), with three on-demand exceptions · accepted
Nightly match on (new posting, active resume). On-demand only for: new-user backfill, resume update re-match, per-posting deep-dive.
**Why:** the digest requires matching done before send; login is an unreliable trigger. `matches` carries `resume_version` + `trigger` from day one. (Memo 02 §9)

### D-007 · Matching is reasoning, not similarity · accepted
Every rationale states what fits, what does NOT fit, and a verdict. Willingness to say no is a product requirement.
**Why:** a recommender that never says no is one nobody trusts. (Memo 01/02, CLAUDE.md)

### D-008 · Verification before digest · accepted
Every apply link must resolve before a posting ships; failures are quarantined.
**Why:** one fake posting costs more trust than ten real ones earn. (CLAUDE.md)

### D-009 · The diff is the product; never delete postings · accepted
Vanished postings are marked `closed`, not deleted — enables death detection + lifespan stats.
**Why:** show what changed, not stale walls; preserve history. (CLAUDE.md)

### D-010 · Delivery: email digest (push) primary, read-only dashboard (pull) secondary · accepted
Dashboard ships end of week 3 (needs the match column). (Memo 02 §10)

### D-011 · Stack: Python + FastAPI + SQLite→Postgres + Anthropic SDK + React · accepted
(CLAUDE.md)

--- decisions made in this build-prep phase ---

### D-012 · Pipeline runtime: local machine (cron/launchd) for week 1 · accepted · 2026-06-11
**Why:** simplest for a stateful nightly job with a local SQLite file; easy to debug. Documented path to a small VPS once it needs to run laptop-closed. GitHub Actions rejected for week 1 (SQLite is ephemeral there).

### D-013 · Transactional email provider: Resend · accepted · 2026-06-11
**Why:** best DX for a solo dev, clean API, generous free tier, simple domain setup. Deliverability is the constraint that matters (a digest in spam is no product).

### D-014 · Python toolchain: uv · accepted · 2026-06-11
**Why:** one fast tool for venv + deps + lockfile; current default for new Python work. Core commands documented in the repo setup doc.

### D-015 · Seed employer data: CSV curated by Hayden, ATS resolved by Claude via live-endpoint probing · accepted · 2026-06-11
Hayden owns `name` + priority columns; Claude probes Greenhouse/Lever/Ashby to mechanically verify `ats_type`/`ats_slug`. A `verification` column (verified/suspect/unverified) makes confidence explicit.
**Why:** mechanical verification beats trusting guessed slugs; the Layer 1 fetcher's 404 is the final arbiter.

### D-016 · Diff identity = ATS `external_id`, NOT fuzzy title-match · accepted · 2026-06-11
The daily diff keys on a stable per-employer external id from the ATS. Fuzzy title+company+location matching is a *separate, later* concern for cross-source dedup only.
**Why:** conflating the two makes the daily diff noisy and wrong. See `docs/04-data-model-spec.md`.

### D-017 · No per-company scrapers; route to generic platform fetchers, else Layer 2 · accepted · 2026-06-11
The ATS-identification pass showed the 54-company universe collapses into ~8 platforms, not 54 bespoke sites.
Build generic fetchers per *platform* (Workday/Greenhouse/Lever/Ashby cover 44%; +iCIMS/Workable/Oracle/SmartRecruiters → ~61%);
the ~30% custom/portal tail goes to **Layer 2 LLM-read**, not hand-written scrapers.
**Why:** N custom scrapers is the documented #1 maintenance/abandonment risk (Memo 01/07). Per-*platform* fetchers
are deterministic AND low-maintenance; the LLM fallback handles the bespoke tail with zero per-company code.
A hand scraper is a deliberate, logged exception reserved for a must-have, high-volume, otherwise-unreachable employer. See `docs/07-ats-routing.md`.

### D-018 · Fetcher build order: Greenhouse/Lever/Ashby → Workday → Tier-B → Layer 2 · accepted · 2026-06-11
Weeks 1–2 ship GH/Lever/Ashby (9 companies, verified). Workday next (15 companies, `cxs` API live-verified).
Then iCIMS/Workable/SmartRecruiters/Oracle. Tier-C singletons opportunistically. Layer 2 absorbs the rest.

### D-019 · Tests run against captured fixtures, not live ATS endpoints · accepted · 2026-06-11
Capture each verified endpoint's response once → golden JSON in `tests/fixtures/`; unit tests assert field
mappings against fixtures (fast, offline, polite). A separate opt-in `live` smoke test hits real endpoints to catch ATS drift.
**Why:** live calls in the normal test loop are flaky, slow, and hammer the ATS.

### D-020 · Four-level test taxonomy; default suite is fast/offline/free; LLM evals are a path-filtered merge gate · accepted · 2026-06-11
Tests are organized unit → integration → system → e2e, pushed down the pyramid. Default `pytest` runs
unit+integration+system (deterministic, no network, no LLM cost); `live`/`e2e` are opt-in, never block a merge.
LLM behavior (match/extraction) is mocked in levels 1–3 and pinned by a small **eval** suite: structural properties
(verdict enum, non-empty fits AND gaps per D-007, level enum) block hard and need no live call; behavioral cases
(the "obvious no" must return `no`) call the real model and gate on a threshold/majority over a small golden set.
The eval suite **is a CI merge gate, but only runs on PRs touching prompt/matching/extraction code** — so it guards
the one trust-critical output (the digest) without taxing unrelated PRs with tokens or flake. Bug fixes start with a
failing regression test. Full spec: `docs/08`.
**Why:** the code is model-written, so tests are how we trust it; fast deterministic tests stay green and get run,
slow/flaky ones rot; LLM output can't be asserted by string equality but its contracts can be, and a prompt
regression that ships bad rationale costs more trust than the cents the gate costs to catch it.

### D-021 · Definition of Done + automated gates + mandatory human diff review · accepted · 2026-06-11
Nothing merges to `main` (always-releasable) without: green default suite, `ruff` format+lint, `mypy` (chosen over
pyright), secret-scan, `uv lock --check`, and — on prompt/matching/extraction PRs only — the path-filtered `eval`
gate (D-020) — run identically as pre-commit and CI (evals CI-only) — **plus** an automated `/code-review` and a
human reading the full diff. Small single-idea PRs; docs (`WORKLOG` always, `DECISIONS`/specs as touched) updated as
part of DoD. Deliberately skipped for now: staging envs, coverage-% gate, gitflow, formal issue tracker. Full spec: `docs/09`.
**Why:** with a model writing nearly all code, the human's leverage is the review gate + machine-enforced bars, not
the typing; unreviewed AI code is the project's top risk, and a small diff is the only reviewable one.

### D-022 · Grid/power (energy) is the first-built vertical; aviation is the week-4 architecture-test add · accepted · 2026-06-11
Build order is energy-first: weeks 1–2 stand up Layer 1 against the grid/power universe (the seeded, ATS-verified
one — D-015/D-017). Aviation is **not yet seeded** and becomes the week-4 "vertical = config" exam (D-004 / `docs/06`).
Supersedes the earlier CLAUDE.md build-sequence wording that said "weeks 1–2 aviation only / week-4 add energy" —
that contradicted the seed data and `docs/06`, which already treated aviation as the added vertical.
**Why:** you build against the data you actually have verified; energy is curated and endpoint-checked today, aviation
isn't. The fetcher is vertical-agnostic (D-004), so "first vertical" only picks which seed the week-1 fetch runs over.

### D-023 · Two-stage cheap filtering precedes the LLM match rationale · accepted · 2026-06-11
Before the strong model writes any resume-match rationale, two cheap, deterministic gates run:
- **Stage A — scope/relevance gate (free, at Layer 1 on the title):** is this posting even in-scope for the vertical
  (e.g. software/data role, US, early-career)? Runs on the fetched **title/keywords before any LLM extraction**, so
  out-of-scope roles (senior, non-eng, wrong geo) are dropped at zero token cost. Resume-independent.
- **Stage B — match pre-filter (cheap, post-extraction):** for postings that pass Stage A, a level/location/work-auth
  gate decides which are worth spending the strong model on for a given resume → writes `matches.score`. Resume-aware.
- Only Stage-B survivors reach the strong-model rationale (which must still state fits/gaps/verdict — D-007).
Full mechanics deferred to the week-3 matching spec; this entry fixes the **shape** so it isn't re-litigated.
**Why:** the strong model is the one real cost (D-005); spend it only on postings already known to be in-scope and
plausibly-matched. The free title-level gate is the cheapest filter and was previously only implied, not specified.

### D-024 · Freshness: digest relies on the diff; backfill caps at 2 weeks · accepted · 2026-06-15
Application success drops sharply ~1–2 weeks after a role is posted, so output must skew fresh. Policy:
- **Nightly digest needs no staleness expiry** — because it's a *diff*, each posting is surfaced **once, the night
  it's first detected** (it enters the `new` set), never re-shown while it stays open. Freshness is automatic; a job
  open for weeks does not reappear or clutter the digest. This is the strict-daily behavior (D-009 / `docs/04` lifecycle).
- **New-user backfill caps at ~2 weeks** — backfill matches the resume against *all currently-open* postings (D-006),
  where every open role is "new to us" even if posted months ago. Cap to postings within ~14 days, preferring the
  ATS `posted_at` (Greenhouse `first_published`/`updated_at`, Ashby `publishedAt`, Lever `createdAt`) and falling back
  to `first_seen_at`. The 14-day figure is a starting default, tunable against the per-company **lifespan data** the
  diff already collects (`closed_at − first_seen_at`).
- **Dashboard ages out / flags old open postings** — the one pull surface that shows the full open set, so it (unlike
  the digest) needs an explicit recency treatment.
Full mechanics deferred to the **week-3 digest/matching spec**; this entry fixes the **policy** so it isn't re-litigated.
**Why:** the diff gives daily freshness for free, so a cap only matters where we present the whole open set (backfill,
dashboard); a hard flood of months-old roles at signup would bury the timely ones and falsify the "apply fast" value.

**Amendment (2026-06-21, D-039):** the **backfill cap is now 5 days, not ~14** (the 14d figure was always
flagged a tunable starting default), and it is **decoupled from the dashboard's "Two weeks" toggle** (which stays
14d). They now share only the *windowing predicate* (`COALESCE(source_updated_at, first_seen_at) >= cutoff`), not the
number. Also settled: **nightly matching is NOT capped** — the digest already keys its `new` set on `first_seen_at`
vs `last_sent_at`, so old backlog can't flood the inbox; the cap is the backfill's job alone. See D-039.

### D-025 · DB access = SQLAlchemy Core + Alembic; SQLite now → Postgres at first hosted deploy · accepted · 2026-06-15
The persistence layer is **SQLAlchemy Core** (not ORM) with **Alembic** migrations. Schema lives in
`vja.db.schema` as Core `Table`s; engine/URL in `vja.db.engine` (`VJA_DATABASE_URL`, default local SQLite, with a
`PRAGMA foreign_keys=ON` listener). Enums are `VARCHAR`+`CHECK` on both dialects (`native_enum=False`). Run **SQLite
locally and in tests**; cut over to **Postgres at the first hosted/demo-user deploy** (~2 weeks out — 2 demo users
incoming), which is just a URL swap + `alembic upgrade` because Core is dialect-portable. Refines D-011 (stack) /
D-012 (local runtime → VPS).
**Why:** Core keeps the actual SQL legible for the review gate (D-021) while giving near-free dialect portability, so
the imminent Postgres move (driven by *hosting* for demo users, not load) costs a config change, not a rewrite. ORM
rejected: too much abstraction for a single-writer 7-table schema, and it hides the SQL we most need to review.

### D-026 · Phase/Block terminology + Workday pulled ahead of Layer 2 & dashboard · accepted · 2026-06-16
Two things. **(1) Terminology:** work is organized as **Phases** (themed milestones) made of **Blocks** (PR-sized
units); "chunk" is retired (Phase-1 chunks 1–6 were blocks). **(2) Build order:** the **Workday fetcher moves up** to
**Phase 4 — right after the bare digest (Phase 3) and before Layer-2 matching (Phase 5) and the dashboard (Phase 6)**.
Phase roadmap of record: P0 docs ✅ · P1 core logic ✅ · P2 persistence/L1 (finishing) · P3 bare digest (proof of
loop) · **P4 Workday** · P5 extraction+matching · P6 dashboard · P7 aviation vertical · P8 remaining coverage
(Tier-B, HN/niche) · P9 discovery agent · cross-cutting hosting/Postgres cutover (D-025).
Supersedes the week-based CLAUDE.md/README build sequence that placed Workday "after" matching/dashboard. Consistent
with D-018 (Workday already ranked second among fetchers).
**Why:** the digest's value is coverage, and Workday is the single biggest bucket (15/54) holding the high-volume,
meaningful employers (Vistra/S&P/Shell/Duke/PJM…) — adding it ~doubles coverage to 24/54. It's pure Layer 1 and
independent of the LLM, so it has no reason to wait behind matching; building it right after the digest also de-risks
the gnarliest fetcher early and lets it ride on Phase-2 failure isolation + Phase-3 link verification. The bare digest
(P3) still ships first on the 9 easy fetchers so the riskiest fetcher never gates the proof-of-loop milestone.

### D-027 · Digest recipient: env var now → `profiles` at Phase 5 · accepted · 2026-06-17
For the bare digest, the recipient is the `VJA_DIGEST_RECIPIENT` env var (single user — the builder). At Phase 5 the
recipient resolves from active `profiles` rows per vertical; the `profiles` table already exists in the schema, so this
is a source swap, not a model change. Multi-user/auth becomes operationally real at the D-025 hosting/Postgres cutover.
**Why:** a "user" in this product is a *resume + vertical + email* (the rationale matches against the resume), and the
bare digest has no resume/matching yet — a `profiles` row would be half-empty. The env var is a deliberate bridge that
keeps `digests.recipient` carrying a real address without standing up signup/auth before there's anything to match.

### D-028 · Empty digest = skip send (no email, no `digests` row) · accepted · 2026-06-17
When a digest has zero new AND zero closed postings, send nothing and write no `digests` row. The `pipeline_runs` row
still records that the run happened. (An all-quarantine night — new candidates all failed verification — logs the
quarantine count to stderr so it isn't silent.)
**Why:** the product hypothesis rests on the builder continuing to open the digest (the kill criterion). A recurring
"nothing changed today" email trains the reader to ignore it; every email that arrives must carry real signal.

### D-029 · Resend via raw httpx; sandbox sender for the proof-of-loop · accepted · 2026-06-17
The Resend send (D-013) is a single `httpx.post` to `https://api.resend.com/emails`, not the `resend` SDK. Sender
defaults to the sandbox `onboarding@resend.dev` (override via `VJA_DIGEST_FROM`); `RESEND_API_KEY` from env (the local
`.env` may spell it `resend-api-key` — both accepted, since hyphenated names can't be shell-exported, only
dotenv-loaded). A `pending` `digests` row carrying the full contents JSON is written *before* the POST, then finalized
`sent`/`failed` — mirroring the `pipeline_runs` running-tombstone so a crash/failed send leaves a durable record.
**Why:** httpx is already a dependency and `respx`-mockable (no new dep, offline tests); the sandbox sender needs only
an API key to prove the loop end-to-end (it delivers only to the account-owner email — verify a domain to send wider).

### D-030 · Dashboard v1 includes recency toggles; freshness = ATS posted/updated date · accepted · 2026-06-17
The v1 dashboard is **not** a static four-column mirror of the digest — it includes **recency toggles** over the full
open set, which is the feature that justifies a pull surface existing beside the push digest (a once-a-day email
structurally can't offer "show me everything updated this week"). Refines D-010; relaxes the "deliberately minimal /
no logic of its own" framing in Memo 02 §76 / CLAUDE.md (that was early scope-control, not a hard constraint).
- **Toggle set:** *New today* (mirrors the digest's `new` set — keyed on **`first_seen_at`**, i.e. our detection),
  *This week* (≤7d), *Two weeks* (≤14d — same window as the D-024 backfill cap), default *All open* with stale
  flagging (D-024 b3). Shared recency vocabulary across digest, backfill, and dashboard.
- **Recency criterion = ATS activity date.** A posting falls in a window if it was **posted *or* updated within it**,
  using the most recent ATS-supplied date (Greenhouse `updated_at`, Ashby `publishedAt`, Lever `createdAt`),
  normalized to UTC, falling back to `first_seen_at` when the ATS gives nothing. (*New today* alone uses
  `first_seen_at` so it equals the digest.)
- **Shared infra (build once):** persisting + normalizing that ATS date powers three things — the Phase-5 backfill
  2-week cap (D-024 b1), these dashboard toggles (D-024 b3), and future apply-speed/lifespan signals. Fetchers already
  capture the date into `RawPosting`; `insert_posting` currently drops it, so the work is: normalize per-ATS → persist
  (small migration) → query. It lands with **Phase 5** (backfill needs it first); the **Phase 6** toggles then consume
  it with no new backend date work — so nothing in the roadmap reorders.
**Why:** a read-only mirror of digest data gives the user no reason to open the dashboard; recency views are its reason
to exist. Keying "fresh" to ATS dates (not our content-change detection) means freshness reflects what the *employer*
actually did, which is exactly what the "apply fast" thesis (D-024) depends on.

### D-031 · Nightly scheduling: launchd + one-process `vja-nightly` + alert-on-hard-failure · accepted · 2026-06-17
The unattended nightly run is a single console command, **`vja-nightly`** (`src/vja/nightly.py`), composing
`run_pipeline` (all verticals, one pass) then `send_digest` per vertical — one process, one log, one exit code.
- **Scheduler = macOS launchd** (LaunchAgent, `deploy/launchd/`), daily 06:00 local. Chosen over cron because
  `StartCalendarInterval` runs a **missed job when the Mac wakes from sleep**; cron silently skips it. APScheduler
  rejected (needs a long-lived process — wrong for a laptop). Refines D-012 (local cron/launchd, week 1).
- **Failure surfacing (the run is unmonitored):** on a **hard failure** — pipeline `status==failed`, or any digest
  send `failed` — `vja-nightly` emails an alert (reusing the Resend path) and exits non-zero. Partial fetch failures
  are logged and included in the alert body but don't by themselves alert (anti-noise, cf. D-028). If the alert send
  itself fails (Resend down), it's logged, not raised.
- **Portability (standing principle; cloud cutover D-025):** the scheduler is a swappable trigger; the durable core is
  the `vja-nightly` command + env/`.env` config + `VJA_DATABASE_URL`. macOS-specific surface is confined to
  `deploy/launchd/` (plist + 2 scripts). Cutover adds a `deploy/<platform>/` trigger + secrets + a Postgres URL swap —
  no rewrite. Two rules keep it portable: (1) the app logs to **stdout/stderr** and the trigger routes them (never
  hardcode log paths); (2) schedule time + secrets are environment config, not code. launchd's catch-up is laptop-only
  (servers don't sleep → plain cron suffices), and Postgres unlocks GitHub Actions cron (rejected before only for
  SQLite ephemerality, D-012).
**Why:** completes Phase 3's proof-of-loop as a *recurring* product, not a thing you remember to run; the sleep
catch-up is the deciding factor for a laptop; an active alert is required precisely because nobody watches the run.

### D-032 · Workday `cxs` fetcher: list-only + paginate-or-fail · accepted · 2026-06-17
One generic `WorkdayFetcher` (`src/vja/fetchers/workday.py`) handles all Workday tenants via the per-tenant config
already in the seed — no per-company code (D-004/D-017). It's a **POST** to the cxs `/jobs` endpoint, paginated by
`offset`. Two contracts:
- **List-only.** The cxs list omits the job description; we map from the list alone (`description=None`). The full
  description is a Layer-2 concern, fetched lazily per *new/changed* posting later — fetching it here would mean
  hundreds of needless requests per big tenant (S&P 234, Vistra 193) for data Layer 1 doesn't use. The one tradeoff:
  `content_hash` won't notice a description-only edit (accepted — the diff keys on `external_id`).
- **Paginate fully or fail (never partial).** Page until the collected count reaches `total`; any page error → the
  whole employer fails (`FetchError`), and a short final tally also fails loudly. A truncated/partial list would read
  as mass closures — this is the fetcher-level half of the false-closure guard (the pipeline-level threshold guard is
  P4.3). Mapping: `external_id = externalPath` (stable, unique — D-016), `apply_url` = public board URL built from the
  cxs host + site + `externalPath` (confirmed live), `location = locationsText`, `updated_at = None` (Workday's list
  gives only a relative `postedOn` — a weak spot for D-030). The **3 `detected` tenants** (BP, GE Vernova `SITE_TBD`;
  Castleton prefix) are parked `proposed` in the seed until P4.2 live-verifies their endpoints.
**Why:** Workday is the biggest coverage bucket (15/54); the generic fetcher took live coverage 9 → 21 fetchable
employers (+1131 postings on first run). List-only keeps it polite/fast; paginate-or-fail keeps the diff trustworthy.

**P4.2 update (2026-06-18):** onboarded the 3 parked tenants from human-pulled board URLs (config only, zero fetcher
code — D-004 again): **GE Vernova** (`Vernova_ExternalSite`, ~2381), **BP** (`bpCareers`, ~414), and **Fluence**
(reclassified custom→Workday, ~108) → coverage 21 → **24**. Bumped the Workday timeout 20 → 30s (BP's board is slow,
>20s). Findings worth keeping: **`osv-` Workday hosts** (e.g. Castleton `osv-cci.wd1`) **422 the cxs API** — the board
renders but exposes no clean JSON, so they route to Layer 2, not a Workday fetcher. Enverus = Jobvite (Tier-C, no
fetcher yet); Aurora unidentified → Layer 2.

### D-033 · Resume input abstracts to `resume_text`; non-text formats are a signup-time adapter · accepted · 2026-06-18
The matching profile stores `profiles.resume_text` (plain text), and the matcher reads text — so the *input format*
is decoupled from everything downstream. For now (single user, config-driven) the resume is supplied as markdown via
the vertical YAML's `matching_profile.resume` path. When real users sign up (multi-user / D-025 era), **PDF (and other)
resumes are handled by a small input adapter at the upload boundary** — `pdf→text` (`pypdf`/`pdfplumber`/PyMuPDF for
text PDFs; OCR or Claude's native PDF document input as a fallback for scans) — landing plain text in `resume_text`.
**Why:** it's purely an ingestion concern, with **no schema, matching, or extraction impact** (the seam is already at
`resume_text`), so format support never gates Phase 5; it slots into the signup flow when there's a signup flow to slot
into. Recorded now so the future path is explicit rather than rediscovered.

### D-034 · Stage-A scope gate = config-driven whole-word keyword filter, computed on-the-fly · accepted · 2026-06-18
Implements D-023's Stage A. A posting's **title** is in-scope iff it matches ≥1 `role_include` keyword
AND no `exclude` keyword — whole-word, case-insensitive (`src/vja/scope.py`). Keyword lists live in the
vertical YAML's `scope` section (config, not code — D-004), so tuning needs no code change. The verdict
is **computed on-the-fly** when selecting postings to extract/match (5.2), **not persisted** — no
`postings.in_scope` column, no migration; the gate is free + deterministic so recomputing each run is
cheap, and postings are never dropped from the DB (the diff still tracks them all for closure detection).
**Why:** the cheapest possible filter (zero tokens, no model) drops the bulk of a whole-company board
before any paid work. Empirically on the grid universe it kept **400 of 1697 open postings (23%)** with
correct drops (senior/non-software/ops) — a 77% cut to Layer-2 cost. Keyword matching is deliberately
coarse; Stage B (post-extraction) + the LLM refine. Chose whole-word over substring to avoid false hits
(`ml`→"html"); accepted the tradeoff that it won't catch a keyword embedded in a larger word
(`data`→"database"), which other includes/role words cover.

### D-035 · Layer-2 extraction: Haiku, all-LLM, cached by content_hash, Workday desc via cxs detail · accepted · 2026-06-19
`src/vja/extract.py` turns in-scope postings into structured fields (`level`/`location`/`remote`/`work_auth`/
`stack`/`comp_*`/`posted_at`) via `client.messages.parse` on the **cheap tier Haiku 4.5** (`claude-haiku-4-5`,
the D-005 tiering — the SDK default is Opus; quality is gated by the eval, bump to Sonnet only if it
underperforms).
- **All-LLM** (no per-field hybrid): the description dominates input cost and must be sent regardless, so
  hybrid saves rounding-error while adding per-ATS parsing. **Synchronous** calls (latency lands in-process;
  absolute spend is pennies, so the Batches 50% discount isn't worth async polling).
- **Cached by `content_hash`**: extraction runs only on open postings with `extracted_at IS NULL` that pass
  Stage A; `update_changed` nulls `extracted_at` on a content change → re-extract. One-time ~1k backlog
  (~$0.55–1.10), then pennies/night. Cost metered from `usage` (Haiku rates).
- **Workday descriptions pulled at extraction** via the cxs detail endpoint (`WorkdayFetcher.fetch_detail`) —
  the "lazy Layer-2 fetch" D-032 anticipated; scoped to in-scope + cached (~500 one-time GETs, not the
  Layer-1 N+1 storm). Bonus: real posted date + structured `country`. So **every source gets full extraction**.
- **Geo filtering deferred to Stage B** (5.3) over the extracted location/country — no fuzzy pre-filtering here.
- **Evals (D-020):** offline unit/integration mock the SDK; an opt-in `eval` runs real Haiku on a fixture
  (structural + an obvious senior/US case), the path-filtered merge gate.
**Why:** extraction is the one resume-independent, cacheable LLM step; spending the cheap tier once per
posting (Stage-A-gated) keeps Layer-2 cost in the cents while giving matching (5.3) the structured fields +
descriptions it reasons over. Prereq: `ANTHROPIC_API_KEY` in `.env`.

### D-036 · Stage-B pre-filter + matching: Sonnet, fits/gaps/verdict/score, prompt-cached, eval-gated · accepted · 2026-06-19
Closes the two-stage filter (D-023) and writes the first `matches` rows (`src/vja/prefilter.py`,
`src/vja/match.py`, `src/vja/db/matches.py`).
- **Stage B** (`passes_prefilter`) is a cheap, deterministic gate over the *extracted* fields that
  decides which Stage-A survivors earn the strong model for a given resume. Coarse by design (like
  Stage A): it drops only **confirmed** out-of-range postings — a concrete `mid`/`senior` level, or a
  clearly non-US `location` (US-signal allowlist: postal codes + full state names + `United States`/
  `USA`/`America`/`remote`, whole-word + case-insensitive). `unknown`/null/`remote` **pass** — dropping
  a plausible match is worse than spending a few cents to let the LLM rule it out. `work_auth` is **not**
  a hard gate (the config carries no allowed values and the candidate's own auth status isn't encoded);
  it's surfaced to the matcher as a signal. Knobs are the vertical YAML's `prefilter` (D-004).
- **Matching** runs the **strong tier (`claude-sonnet-4-6`)** — *not* Haiku. Extraction is mechanical
  (Haiku's job, D-035); matching is judgment and the user-visible, trust-critical output, so it gets the
  strong model (D-005 tiering). The model emits a structured `MatchResult` (verdict ∈
  strong_yes/yes/maybe/no, 0–100 score, non-empty fits AND gaps, a one-line rationale) mapping 1:1 to the
  `matches` columns; the willingness to say *no* is enforced in the prompt + pinned by the eval (D-007).
  Adaptive thinking on; resume + instructions are the **prompt-cached prefix** (stable across every
  posting in a run), only the per-posting structured fields are volatile.
- **Idempotent + isolated:** one `matches` row per (posting, profile, resume_version); a re-run only
  matches the unmatched remainder; a single posting's failure is logged and skipped (mirrors extraction).
  `trigger=nightly`. No schema change — the `matches` table pre-existed.
- **Clarifies D-023's "Stage B writes `matches.score`":** Stage B persists **nothing** — it's an
  in-memory filter (a non-survivor can't have a row, since `verdict` is NOT NULL). **`score` is the LLM's
  0–100 output**, written with the rest of the rationale. Cost is **eval-gated** (D-020): bump Sonnet→Opus
  only if it underperforms (the same cheap-tier-with-escape-hatch pattern 5.2 used for Haiku→Sonnet).
**Why:** the strong model is the one real cost (D-005), but the two gates bound the set hard (1697 open →
~400 Stage-A → ~50–150 Stage-B survivors), so a one-time backfill is ~$2 on Sonnet and steady state is
pennies/night — making model choice a quality decision, not a cost one. Resolved with Hayden:
Sonnet (not Haiku), Stage-B + matching as one block. Not in this block: digest rationale + nightly wiring
(5.4). Prereq: `ANTHROPIC_API_KEY` in `.env`.

### D-037 · Phase 5.4: digest rationale + nightly extract→match→send + recipient→profiles · accepted · 2026-06-19
Closes Phase 5 by composing the Layer-2 pieces (5.1–5.3) into the nightly loop and putting the match
rationale in the inbox. Three wiring seams:
- **Digest rationale + gating.** A digest is now per **(vertical, profile)**: its `new` set is the open
  postings that earned a *relevant* match for that profile's `resume_version` — verdict ∈
  **{strong_yes, yes, maybe}**, **sorted by score desc**. `no` verdicts and unmatched/out-of-scope
  postings drop out (an all-`no`/all-out-of-scope night skips via D-028). The body shows
  `[verdict · score]` + the one-line `rationale`; `fits`/`gaps` persist in the `digests.contents` audit
  JSON but are **not** rendered (scannability). Closures stay vertical-global, no rationale.
  (`build_digest` now joins `matches`; `last_sent_at` keys on (vertical, **recipient**) so each profile's
  window is independent.)
- **Nightly composition.** `vja-nightly` runs `run_pipeline` → for each config-backed vertical
  `run_extraction` → `run_matching` → `send_digest` per active profile (the CLAUDE order
  fetch→diff→extract→match→verify→send). The Layer-2 pass is an injected seam (`run_layer2`, mirroring
  `resolve_fetcher`) so the orchestrator tests stay fully offline. Per-vertical isolation: one vertical's
  Layer-2 error is logged and skipped, never aborting the run. The run's LLM totals (extraction/match
  calls + est cost) are written to the `pipeline_runs` row via `update_llm_metrics` (the columns
  `finish_run` had stubbed at 0 "no LLM yet").
- **Recipient → profiles (realizes D-027).** The digest recipient is the matched **profile's
  `user_email`**, not an env var. `VJA_DIGEST_RECIPIENT` is **repurposed as the ops/alert recipient**
  (where nightly failure-alerts go) — still required, since the builder is the ops contact.
**Scope (decided with Hayden):** the three wiring items only. ATS `posted_at` normalize→persist→query
(D-030) and new-user backfill (D-024) stay **deferred to the backfill block** — the docs peg that work to
Phase 5 *because backfill needs it first*, and the nightly digest is a diff that reads no `posted_at`. The
DRW malformed-`posted_at` row (D-035) stays parked with that same future work. No schema change.
**Why:** matching is the product (D-007), so the rationale has to reach the inbox, gated to what's worth
reading — a once-a-day email of every new posting (incl. roles the model says *no* to) would train the
reader to ignore it (the kill criterion). Per-profile addressing is the natural unit now that a "user" is
a resume+vertical+email; deferring the date work keeps this block small and honors the docs' sequencing.

### D-038 · Phase 6 · A1: normalized ATS activity date (`postings.source_updated_at`) · accepted · 2026-06-21
Builds the date infra D-030/D-024 promised for Phase 5 but D-037 deferred — the dashboard's recency
toggles + the backfill cap need one normalized, queryable date. New nullable column
`postings.source_updated_at` (`UTCDateTime`), fed by a tolerant normalizer (`src/vja/dates.py`).
- **One normalizer, tolerant by contract.** `normalize_ats_date(str|None) → datetime|None` collapses every
  shape — ISO 8601 (offset/`Z`/naive→UTC/date-only), epoch seconds/millis digit-strings (Lever) — to
  tz-aware UTC; **anything unparseable returns `None`, never raises.** A posting must never fail to persist
  on a bad date. This is also where the parked **DRW malformed-`posted_at`** row (D-035) is resolved: it
  normalizes to `None` → falls back to `first_seen_at`. A digit string is only trusted as an epoch when it
  resolves to a posting-era date (year ∈ [2000, 2100]) — so a bare year like `"2026"` returns `None` rather
  than silently becoming 1970 (a garbage date is worse than NULL, which falls back to `first_seen_at`).
- **Source-of-truth rule: L1 `updated_at` is authoritative; L2 `posted_at` fills only when L1 left it NULL.**
  The ATS `updated_at` bumps when the employer touches the posting (exactly "updated within window"); the
  LLM-read `posted_at` is an older, less-reliable body read. So extraction's date only *rescues* date-less
  sources (**Workday**) via a `CASE WHEN source_updated_at IS NULL` — it never overwrites a clean L1 stamp.
  A slight, deliberate departure from D-030's literal "most recent of the two" (better data quality, and it
  avoids dialect-specific `GREATEST`/`max`).
- **Refreshed on *every* sighting (incl. the unchanged `bump_last_seen` path), but only when non-NULL.**
  `updated_at` isn't part of `content_hash`, so a date-only bump lands on the unchanged path — all three L1
  write paths (insert/bump/update) refresh it. The non-NULL guard means a later fetch that omits the date
  never nulls a good value (or Workday's extraction-filled one). Bonus: this **self-heals the existing
  corpus** — GH/Lever/Ashby rows backfill on the next nightly's bump, no data migration needed.
- **Accepted limitation:** existing *Workday* rows are already extracted (extraction won't revisit) and had
  no L1 date, so their `source_updated_at` stays NULL → dashboard falls back to `first_seen_at` for them.
  That's D-030/D-032's acknowledged Workday weak spot; *new* Workday postings get `startDate` via extraction.
- Scope: persist + normalize only. The window **query** + its index (D-030) and onboarding **backfill**
  (D-024) are the next blocks (A2). New repo params are keyword-only/defaulted — nothing else moves.
**Why:** the dashboard's headline feature (recency) and the backfill cap both need a real date, and the
fetchers already capture it (`RawPosting.updated_at`) — `insert_posting` just dropped it. One tolerant
normalizer + one column, fed at the persistence boundary, unblocks Phase 6 without reordering the roadmap.

### D-039 · Phase 6 · A2: recency-window query + index + signup backfill · accepted · 2026-06-21
Consumes A1's normalized `source_updated_at` (D-038) to build the dashboard's recency prerequisite and the D-024
signup backfill — the two consumers D-030 promised would share one date predicate.
- **One match-free window primitive.** `open_postings_in_window(engine, vertical, *, cutoff, by_first_seen)`
  (`src/vja/db/postings.py`) returns open postings in a window, newest-activity-first, **with no match join** — so
  it serves both the dashboard *and* the backfill (which selects postings *because* they have no match yet). The
  dashboard API (B1) layers verdict/score on top with a second query keyed on `(profile_id, resume_version)`,
  honoring the docs/11 `(vertical, profile_id)` seam. The freshness predicate lives once in
  `activity_window_clause(cutoff)` = `COALESCE(source_updated_at, first_seen_at) >= cutoff` and is reused by
  `postings_needing_match(..., since=…)`.
- **Flexible cutoff, not a 4-value enum.** The caller computes the cutoff, so one query covers every dashboard
  toggle *and* the backfill (different cutoffs, same predicate): `cutoff=None` → all open; `by_first_seen=True` →
  window on `first_seen_at` only (the **"new today"** basis = **calendar midnight UTC**, so it equals the digest's
  `new` set, D-030); else → the activity predicate (the *This week* / *Two weeks* toggles + the backfill).
- **Backfill = standalone capped path; nightly untouched.** `run_backfill(engine, vertical, profile)`
  (`src/vja/match.py`, CLI `vja-backfill`) matches one profile against open∧extracted∧unmatched postings whose
  activity date is within the last **5 days** (`_BACKFILL_WINDOW_DAYS`), `trigger=backfill`, idempotent + per-posting
  isolated. `run_matching`'s per-profile loop was extracted into a shared `_match_profile` (`since=None,
  trigger=NIGHTLY` for nightly; `since=now−5d, trigger=BACKFILL` for backfill) — zero behavior change to nightly
  (pinned by the unchanged `test_matching_run.py`). Intended caller: the future signup flow; until then `vja-backfill`
  is the manual entry. **Amends D-024** (14d → 5d, decoupled from the dashboard toggle); see that entry.
- **Index.** `ix_postings_status_source_updated` on `(status, source_updated_at)` (migration `f7164d547f15`); the
  existing `(status, first_seen_at)` index covers the COALESCE fallback half.
**Why:** the dashboard's recency views and the signup catch-up both reduce to "open postings whose freshness date is
within a window" — building that predicate once (match-free) lets the dashboard and backfill share it without the
backfill inheriting a match join it can't use, and keeps the nightly diff (already fresh via `first_seen_at`)
unchanged. Deferring the dashboard's match-quality join to B1 keeps the `(vertical, profile_id)` auth seam where
docs/11 wants it.

### D-040 · Comprehension-debt guards: enforced import layering + derived invariants registry · accepted · 2026-06-21
As the codebase grew (~4.1k LOC, 39 ADRs, 840-line WORKLOG), the binding constraint shifted from *code size* (still
healthy — largest file 377 LOC, clean layering, ~1:1 tests) to **the context required to change the code safely**.
Two cheap, durable guards, both modeled on the existing "gates + docs" discipline (D-021):
- **Import-linter layered contract** (`[tool.importlinter]` in `pyproject.toml`; `uv run lint-imports`; wired into
  pre-commit + CI after mypy). Declares the real dependency stack as law — *lower layers must not import higher* —
  so the clean DAG is machine-guaranteed, not luck. Setup surfaced one pre-existing back-edge nobody had noticed:
  `db.employers → fetchers.registry` (for `SUPPORTED_ATS_TYPES`). Grandfathered via one documented `ignore_imports`
  line (visible + reviewed); any *new* `db → fetchers` edge fails the build. Candidate cleanup: inject the supported
  set from the orchestration layer.
- **`docs/INVARIANTS.md`** — a derived, always-current registry of cross-cutting rules, each pointing to its backing
  ADR. ADRs stay the immutable log (the "why/when"); INVARIANTS is the queryable "what's true now" head. Linked from
  `CLAUDE.md` (read-first in the doc map) so every session loads it. New discipline rule: an ADR that changes a live
  rule must replace the matching INVARIANTS line in the same session.
**Why:** "the codebase is getting too big to understand" was a misdiagnosis — the code is small and well-factored;
what grows unbounded is the accumulated invariant/decision context an agent (or Hayden) must reconstruct each
session. These two guards target *that* directly: one keeps the structure mechanically honest, the other keeps the
shared mental model from drifting out of the 39-and-counting ADR log. **Status:** initial INVARIANTS mined from
D-001…D-039; refactoring the grandfathered edge is deferred (out of scope for this chunk by design).

### D-041 · Phase 6 · B1: dashboard = in-scope universe, matched-by-default · accepted · 2026-06-21
The read API (`GET /api/postings`, `src/vja/api/`) revealed that "full open set" (D-030) was underspecified.
`postings` stores the **raw** open set — every role at the curated employers, **including out-of-scope ones** —
because the Stage-A scope gate (`in_scope`, D-034) runs on-the-fly at extraction and is never persisted. The only
durable in-scope marker is `extracted_at IS NOT NULL` (only in-scope titles ever get extracted). Three tiers
result: **T1** raw open (incl. noise) · **T2** `open ∧ extracted` (in-scope, structured) · **T3** `T2 ∧ a match
for this (profile, resume_version)` (assessed). Decisions:
- **Dashboard universe = T2.** The query floors on `extracted_at IS NOT NULL`; raw out-of-scope roles never appear
  (else a new user is dumped thousands of irrelevant jobs). **Refines D-030**: "full open set" → "full *in-scope*
  open set."
- **Default view = T3 (matched), expressed as match-status not a time clock.** Two orthogonal axes:
  *match-status* — matched-only default; `include_unassessed=true` widens to T2 (unmatched rows carry `None`); and
  *recency* — `window` ∈ {`new_today`,`week`,`two_weeks`,`all`} (default `all`). Default hides `no` verdicts
  (mirrors the digest D-037); `include_rejected=true` un-hides them. The relevant-verdict set now lives once in
  `models.RELEVANT_VERDICTS` (was a private constant in `digest/assembly.py`).
- **Match quality via a dedicated LEFT-JOIN query** (`open_postings_with_match_quality`, keyed on
  `(profile_id, resume_version)`). The A2 match-free `open_postings_in_window` becomes caller-less and is **retired**
  (the backfill uses `postings_needing_match(since=)`, not it).
- **`(vertical, profile_id)` seam** (docs/11 §2): `profile_id` optional → thin default resolves the single active
  profile (404 none / id-not-found; 409 ambiguous). Read-only, localhost, no auth — multi-user/security deferred to
  the D-025 cutover. **Cost note:** the dashboard never triggers a match (D-005), so its window has zero LLM cost —
  the 5-day cap (D-039) governs only the signup backfill, deliberately decoupled from the dashboard window.
**Why:** the dashboard's job is "browse the roles relevant to you," not "mirror the raw ATS dump." Flooring on T2
and defaulting to T3 makes a new user's first view tailored (a few dozen assessed roles), while the in-scope T2
toggle still honors D-030's full-set browsing — without ever surfacing out-of-scope noise.

### D-042 · Phase 6 · B2: dashboard SPA stack, frontend test gate, serving model · accepted · 2026-06-21
B2 is the repo's first frontend, so the cross-cutting choices get logged once. The SPA (`frontend/`) consumes the B1
`GET /api/postings` contract and renders the full D-041 surface (4 recency toggles + the two match-status toggles +
expandable fits/gaps/rationale), styled to `DESIGN.md`. Decisions:
- **Stack = Vite + React + TS**, no router/state lib (one page, fetch + `useState`). **Styling = plain CSS + custom
  properties** (DESIGN.md tokens as CSS vars; no Tailwind — the dense, custom dark theme doesn't want a utility
  framework's config).
- **Frontend tests = Vitest + React Testing Library**, wired into the inner loop and as a path-filtered gate (a
  `frontend-checks` pre-commit hook on `frontend/**.{ts,tsx}` + a parallel CI `frontend` job): `eslint` +
  `tsc --noEmit` + `vitest run`. This is the frontend arm of the "testing is policy" invariant (D-021) — it pins the
  toggle→query-param mapping (client side of the contract), control emission, table render rules, and refetch-on-toggle.
  The server side stays pinned by the Python API tests; the two meet at the typed `PostingRow`/`PostingsResponse`.
- **Serving model:** dev = Vite dev server (`:5173`) talking to FastAPI via **CORS** (`CORSMiddleware`, GET-only,
  origins from `VJA_CORS_ORIGINS`, default the two `:5173` hosts — no new dependency); prod = FastAPI mounts the built
  `frontend/dist` at `/` via `StaticFiles(html=True)`, **only when present**, so tests/CI (no build) and `/api/*` are
  unaffected. The scheduler/cloud cutover (D-025) keeps this same shape.
- **No hardcoded vertical:** added `GET /api/verticals` (distinct active-profile verticals via `active_verticals`); the
  SPA picks the first by default. Keeps the "nothing vertical-specific in code" rule (D-004) intact and is Phase-7 ready.
- **Vitest 3** (not 2) — v2 pins Vite 5 nested, clashing with the top-level Vite 6 plugin types; v3 dedupes on Vite 6.
**Why:** lock the frontend conventions (stack, tests-as-gate, serving) in one ADR so later frontend work has a current
head to read instead of re-deriving them, and so the dashboard ships under the same DoD bar as the Python code.
Read-only/localhost/no-auth still defers multi-user + security to the D-025 cutover (per D-041).

### D-043 · L1-authoritative location + persisted `in_scope` + dashboard two-view · accepted · 2026-06-22
B2 use surfaced a real bug: foreign roles (Mumbai/Bangalore/Mexico City) were rated yes/maybe and the dashboard's
"unassessed"/"rejected" toggles confused everyone. Root cause: **L2 extraction was overwriting the L1 `location`
with `null`.** Fetchers write a structured location at insert (e.g. Workday `locationsText` = "Mumbai, India"), but
`save_extraction` wrote every extracted column unconditionally, and Haiku frequently returns `location=null` — blanking
it. With `location` NULL, Stage-B prefilter's coarse keep-null rule passed the role, and `match._posting_text` omitted
the city, so Sonnet rated it blind. Decisions:
- **`location` is L1-authoritative** (mirrors `source_updated_at`, D-038): `save_extraction` fills it only when the
  stored value is NULL; a non-null L1 location is never overwritten by the model's read.
- **Persist a durable `in_scope` flag** (`postings.in_scope`, bool; migration `d30501b4c8ab`), computed at extraction
  from `passes_prefilter` on the *effective* (L1-authoritative) location. It's the durable Stage-A+B marker D-041
  lamented was missing (`extracted_at IS NOT NULL` was a Stage-A-only proxy that ignored geo/level). Resume-independent
  (the gates are vertical config), so one flag per posting is coherent. The matcher still computes the gate live from
  the same pure functions — no drift.
- **Dashboard = single Matched/Cleaned view; rejected (`no`) never shown.** Supersedes D-041's two additive
  checkboxes (`include_unassessed`/`include_rejected`), which read as exclusive buckets but added rows onto the matched
  default — the confusion. Now `view` ∈ {`matched` (default, relevant matches only), `cleaned` (the whole in-scope
  US-software universe incl. unassessed)}; `no` is excluded in **both** (mirrors the digest, D-037). The query floors
  on `in_scope IS TRUE`. Recency axis (`window`) is unchanged.
- **Corpus repair is a separate step** (WS5, its own branch): re-derive `location` from `raw_payload` per ATS, recompute
  `in_scope`, delete matches whose posting now fails Stage B, then re-run `vja-match`.
**Why:** the cheap deterministic gate is the product's cost governor and the "cleaned list" is itself a useful surface;
silently nulling the field it keys on broke both. Making location L1-authoritative + persisting the gate makes "cleaned
= US software" a real, queryable tier and collapses the dashboard to the two views a user actually wants.

### D-044 · Stage-B non-US country override (state-code collision) · accepted · 2026-06-22
With locations repaired, a residual leak remained: bare 2-letter country codes that double as US state codes
("Bengaluru, India, **IN**"=Indiana, "Cordoba, Argentina, **AR**"=Arkansas, "**DE**"=Delaware/Germany) passed Stage B
because the prefilter treats any whole-word state code as a US signal. Decision: add an explicit `_NON_US_COUNTRY_NAMES`
override in `prefilter.py` — a location naming a foreign country **fails** Stage B even when a state code coincidentally
matches. Deliberately omits names that are also US places ("mexico"→New Mexico, "georgia"→the US state), which lean on
the absence of a US signal instead; bare ambiguous codes with no country name ("Munich, DE") stay a coarse-gate residual
the now-location-aware Sonnet match backstops. **Why:** "City, Country, CODE" is the common foreign ATS pattern, and a
named country is an unambiguous signal — cheap to catch deterministically rather than spend a Sonnet call to reject.

### D-045 · Cleaned view = the whole in-scope set, incl. rejected · accepted · 2026-06-22
Live use of the D-043 dashboard revealed that "rejected never shown" makes the two views collapse: once the corpus is
fully assessed, *Cleaned* (in-scope minus `no`) equals *Matched* (relevant only), so the toggle does nothing. The
builder's intent for *Cleaned* is the **objective US-software job list** — "these are the in-scope roles, the same list
for anyone" — independent of the AI's verdict (a user may distrust the match, or have a stale résumé). Decision: the
*Cleaned* view returns **every** in-scope open role — `strong_yes`/`yes`/`maybe`/`no`/unassessed — applying no verdict
filter; the per-profile match columns are decoration on a profile-independent set. *Matched* is unchanged (this résumé's
relevant verdicts only). **Amends D-043**: `no` is hidden from *Matched* and the digest (D-037), but **shown in Cleaned**.
**Why:** the cleaned list's job is coverage/browse, not recommendation — filtering it by the AI verdict defeats its
purpose and made the toggle inert. Matched stays the curated recommendation surface.

### D-046 · Phase 7: aviation vertical shipped as config-only (the D-004 architecture test) · accepted · 2026-06-22
Phase 7 stood up the **aviation_software** vertical — the Week-4 architecture test D-002/D-004 reserved — and it
required **zero `src/` changes**: a vertical is (still) just curation + config. The deliverable was exactly the three
data artifacts `docs/06` predicted:
- **Seed:** 36 aviation employers across every sub-domain (airlines · avionics · OEM/manufacturers · GDS/airline-IT ·
  flight-data/analytics · ATM/infrastructure · eVTOL/autonomy · travel-tech), ATS-resolved by the same live-probing
  pass as grid (D-015) — 7 verified/fetchable (Boeing/Airbus/Wisk Workday, Shield AI Lever, Beacon AI Ashby, OAG/FLYR
  Greenhouse), the rest detected/Layer 2. Probing caught a Greenhouse name collision (`archer` = a veterinary clinic,
  not Archer Aviation) — the probe-don't-guess discipline (D-015) paying off.
- **Config:** `config/verticals/aviation_software.yaml` (aviation domain vocabulary + Stage-A scope + Stage-B
  prefilter) — auto-discovered by `available_verticals()`'s glob, loaded by the same `load_vertical_config`.
- **Résumé:** `hayden_aviation_resume.md` (aviation-tilted; the grid résumé was re-tilted in the same Phase-7 work).
The whole pipeline ran end-to-end with no per-vertical branch: import → load-profiles → fetch/diff (Stage-A) →
extract → match, the same code as grid.
**Bonus finding (not a defect):** the run **stress-tested the Workday fetcher** — Collins/RTX's whole-conglomerate
`cxs` board (4160) exceeds Workday's ~4000 offset cap, so the paginate-or-fail guard (D-032) correctly refused the
truncated page rather than reading 160 roles as closures. Per the **Castleton precedent (D-032)**, RTX was
**reclassified to Layer 2 in config** (no code change) — a known-incomplete board routes to Layer 2 until a
capped-board fetch strategy exists. This is the first Workday tenant large enough to hit the cap (grid's biggest was
GE Vernova ~2376). Logged as a candidate future fetcher improvement (offset-cap-aware Workday pagination).
**Why:** the entire expansion thesis (D-001/D-002) rests on "a vertical is config." Adding aviation with zero code
change — and only a *config* reclassification when a real fetcher limit surfaced — is the thesis holding under test.
Run metrics (postings fetched, in-scope, verdict spread, grid re-match) are in WORKLOG.

### D-047 · Roadmap resequence: cloud + full frontend pulled ahead of the discovery agent · accepted · 2026-06-22
Reordered the back half of the roadmap. **Was:** P8 remaining coverage → P9 Layer-3 discovery agent → cross-cutting
hosting/Postgres cutover (D-025, "triggered by demo users"). **Now:**
- **Phase 8 — Remaining coverage** (unchanged; kept first — more coverage makes a user-facing launch worth more, and
  it likely surfaces new decisions worth having before exposing the product).
- **Phase 9 — Cloud migration + full product frontend.** Promotes the floating D-025 cutover into a real numbered
  phase **and widens it** to the multi-user product surface: auth/login, résumé **upload** (the D-033 adapter at the
  signup boundary), vertical toggle, signup→backfill. The existing Phase-6 dashboard SPA goes from read-only/
  single-user to authed/multi-user. `docs/11` (multi-user & hosting ledger) is this phase's checklist.
- **Phase 10 — Layer-3 discovery agent.** Demoted from P9. Non-essential nice-to-have; relatively simple (shell +
  formatting around an Opus deep-web-search that writes `proposed` employer rows). Doesn't gate a launch, so it waits.
**Why:** the goal shifted to *getting something real in front of users* sooner — that makes hosting + the product
frontend the priority and the discovery agent a later add-on. D-025 stops being an ambient "slot it whenever" item
and becomes Phase 9's spine. **Security/abuse posture is explicitly in Phase 9 scope** (per the launch-readiness
discussion): the dominant risk for a free public signup is **cost-abuse** (each signup spends LLM tokens on backfill),
addressed by email-verify + signup rate-limit/captcha + a per-user backfill cap (D-039) + a global spend ceiling, with
résumé **PII** (encrypt at rest, delete path, never log) and standard web hygiene (managed auth, Cloudflare in front,
secrets in env) as the rest. Supersedes the build-sequence ordering in CLAUDE.md / D-026's P7→P9 tail.

### D-048 · Phase 8 Tier-B starts with iCIMS via the Jibe `/api/jobs` career-site API · accepted · 2026-06-24
First Phase-8 (D-018 Tier-B) fetcher. A coverage-research pass found we fetch only **34%** of the seeded
universe (grid 24/54, aviation 7/36) and that the aviation vertical looked empty (3 companies, only Boeing
matching) purely for lack of coverage — the US-software employers that match (Garmin, Joby, Alaska, …) were
all dark. **Garmin was the worked example:** seeded `custom`/`layer2` but actually **iCIMS**, so a near-perfect
role was invisible. iCIMS chosen to lead (over the easier Workable/SmartRecruiters) because it is the
highest-coverage Tier-B platform *and* fixes that felt gap.
- **The fetch target is iCIMS *Career Sites* (formerly Jibe), not the legacy portal.** The legacy
  `careers-{tenant}.icims.com` portal is a frame-busted SPA with no clean JSON (domReplacement obfuscation);
  the modern product exposes a clean, unauthenticated **`GET {careers_base}/api/jobs?page={n}&limit={N}`**
  returning `{"jobs":[{"data":{…}}],"totalCount":int}`. Verified **uniform across tenants** (Garmin,
  Constellation, Exelon, SIG, ICE, SITA share every core field), so **one generic `IcimsFetcher`** covers all
  — per-platform, not per-company (D-017/D-004). The payload is **richer than Workday's**: `apply_url`, full
  `description`, and a real ISO `update_date` are in the list response, so there's no lazy detail fetch and
  `updated_at` is populated (a D-030 freshness win). Contract mirrors Workday: **paginate-or-fail** (short
  tally → `FetchError`, never a partial list). `external_id = req_id` (D-016).
- **Auth-gated / non-Jibe iCIMS tenants route to Layer 2**, like SuccessFactors. **Joby** (`/api/jobs` 404 —
  custom site) and **Alaska** (legacy portal, no Jibe API) reclassified `detected → layer2`; ATS for Joby
  unconfirmed (re-probe). A full D-015 fingerprint re-probe of the 38 `layer2` rows found **no other Jibe
  tenants** (Garmin was the only misfiled one) but surfaced **Amadeus + Sabre as Workday** (onboarded this
  session — see below).
- **Coverage:** +6 iCIMS fetchable employers (~1,333 postings) — grid 24→28, aviation 7→9 (iCIMS 6).
  Live-verified: Garmin returns 303 postings incl. US aviation-software SWE roles.
- **Same-session Workday onboards (config-only, D-004):** Hayden supplied two board URLs; **Sabre**
  (`sabre:wd1:SabreJobs`, 150) and **Amadeus** (`amadeus:wd502:jobs`, 135) live-verified and onboarded to
  the existing Workday fetcher → aviation 9→11, total **31 → 39** (Workday 18→20). **Delta/Avature** probed
  and left at Layer 2: it serves per-job schema.org JSON-LD but `delta.avature.net` returns a **202
  bot-challenge** (empty body) to non-browser clients, so there's no clean server-side list API.
**Why:** the long tail collapses into a few platforms (D-017); iCIMS's modern career-site API is one clean
generic fetcher that both advances the D-018 coverage tier and resolves a concrete missed-match the builder hit.

### D-049 · Phase 8 Tier-B: Workable fetcher via the embed-widget JSON API · accepted · 2026-06-24
Second Phase-8 (D-018 Tier-B) fetcher, after iCIMS (D-048). Workable exposes a clean, unauthenticated
**embed-widget JSON API** on a uniform host, so — like Greenhouse/Lever/Ashby — it is one generic
per-platform fetcher (D-017/D-004), not a per-company scraper.
- **The fetch target is the embed widget:** `GET https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true`
  → `{"name", "description", "jobs":[{…}]}`. **`?details=true` is required** for the inline
  `description` HTML (a D-030 freshness win — no lazy detail fetch; `updated_at = published_on`).
  Endpoint is **slug-derivable** (`endpoints.py` `_DERIVED_TEMPLATES`), so the seed carries only
  `ats_slug` — verified live uniform across the two seed tenants (Vortexa, Energy Aspects — D-019).
- **Single response, not paginated** — unlike iCIMS/Workday, the widget returns *all* open jobs in one
  `jobs` array (no `total`/offset). So the false-closure guard (`docs/08`) is the **single-request
  contract** (the Greenhouse/Lever/Ashby pattern, not paginate-or-fail): a clean 200 is the
  authoritative complete set; an empty `jobs` array is a legitimate "0 open"; any transport/parse/shape
  error raises `FetchError` and the diff never runs on a partial list.
- **Mapping:** `external_id = shortcode` (the stable Workable req id, the diff key D-016),
  `apply_url = url` (the public posting page), `title`, `location` = `city, state, country` joined
  (full names feed the Stage-B US-signal prefilter D-036 better than the bare ISO codes in `locations[]`),
  `updated_at = published_on`. Any missing required field (`shortcode`/`title`/`url`) raises `FetchError`.
- **Coverage:** +2 fetchable employers (Vortexa, Energy Aspects — both grid/power; Vortexa
  `detected → verified`), **39 → 41**. Live-verified: Vortexa returns 5 open postings with populated
  `updated_at`; Energy Aspects re-verified (API valid, 0 open). Modest in count, but it adds the Workable
  *platform* (more Workable-grade Tier-C singletons land on it later). **Next:** SmartRecruiters / Oracle HCM.
**Why:** the long tail collapses into a few platforms (D-017); Workable's embed widget is the cleanest
remaining Tier-B API (clean JSON, slug-derivable, single-response), so it's the lowest-risk next coverage
step and follows the documented build order (D-018).

### D-050 · Phase 8 Tier-B: SmartRecruiters fetcher via the public postings API · accepted · 2026-06-24
Third Phase-8 (D-018 Tier-B) fetcher, after iCIMS (D-048) + Workable (D-049). SmartRecruiters exposes
a clean, unauthenticated **public postings API** on a uniform host, so — like Greenhouse/Workable — it
is one generic per-platform fetcher (D-017/D-004), not a per-company scraper.
- **The fetch target is the postings list:** `GET api.smartrecruiters.com/v1/companies/{slug}/postings`
  `?limit={N}&offset={M}` → `{"totalFound": int, "content": [ {...} ]}`. Endpoint is **slug-derivable**
  (`endpoints.py`, bare — the fetcher adds limit/offset per page), so the seed carries only `ats_slug`.
  Live-verified against Vitol (slug `Vitol`, 42 open).
- **List-only + lazy detail (Workday parity, NOT iCIMS-rich).** The list omits the job description and
  any apply URL. The public apply URL is **constructed** (`https://jobs.smartrecruiters.com/{slug}/{id}`
  — verified to resolve), so the apply link needs no detail fetch (D-008). The description lives only on
  the per-posting detail endpoint (`…/postings/{id}` → `jobAd.sections`) and is fetched lazily, per
  in-scope survivor, by Layer-2 extraction via `fetch_detail` (cost discipline, D-035) — exactly like
  Workday (D-032). Contract: **paginate-or-fail** on `totalFound` (short tally → `FetchError`, never a
  partial list → no false closures, `docs/08`).
- **Mapping:** `external_id = id` (the stable posting id + diff key D-016), `title = name`,
  `location` from `location.fullLocation` with empty comma-segments collapsed ("Singapore, , Singapore"
  → "Singapore, Singapore"; the full country name beats the bare ISO `country` for the Stage-B US signal,
  D-036), `updated_at = releasedDate` (a D-030 freshness win).
- **Lazy-detail dispatch generalized.** `extract.py` had a Workday-only `if`; it now routes on a per-ATS
  `_DETAIL_RESOLVERS` map (Workday + SmartRecruiters + Oracle), so adding a list-only ATS is a one-line
  wire-up with no per-company branching. The default resolver dispatches by `ats_type`; the injection
  point stays a single callable (tests unchanged in shape).
- **Coverage:** +1 fetchable (Vitol — grid/power; `detected → verified`), **41 → 42**. Adds the
  SmartRecruiters *platform*; more SmartRecruiters Tier-C singletons land on it later.
**Why:** the long tail collapses into a few platforms (D-017); SmartRecruiters' public API is clean and
slug-derivable, and its list-only shape reuses the Workday lazy-detail path already in the system — low
risk, follows the build order (D-018).

### D-051 · Phase 8 Tier-B: Oracle HCM / ORC fetcher via the Candidate-Experience REST API · accepted · 2026-06-24
Fourth Phase-8 (D-018 Tier-B) fetcher. Oracle Recruiting Cloud exposes a clean, unauthenticated
**Candidate-Experience REST API** on each tenant's Oracle Cloud host; the shape is uniform across
tenants, so it is one generic per-platform fetcher (D-017/D-004).
- **The fetch target is the CE requisitions resource:** `GET {host}/hcmRestApi/resources/latest/`
  `recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations&finder=findReqs;`
  `siteNumber={CX_n}` → `{"items":[{"TotalJobsCount": int, "requisitionList":[…]}]}`. **The `expand`
  param is required** (without it the response is search metadata with no `requisitionList`). Hosts +
  site numbers differ per tenant, so — like iCIMS/Workday — the seed `endpoint` is **explicit
  per-tenant** (not slug-derived). Pagination appends `,limit={N},offset={M}` as `finder` sub-params;
  **paginate-or-fail** on `TotalJobsCount`. Live-verified against Southern Company (host
  `emje.fa.us6.oraclecloud.com`, site `CX_1001`, 105 open).
- **List-only + lazy detail (Workday parity).** The list's `External*Str` description fields are empty
  in list mode; the apply URL is **constructed** (`{careers_url}/job/{Id}` — verified to resolve), and
  the description is fetched lazily per in-scope survivor via `fetch_detail` against the detail resource
  (`recruitingCEJobRequisitionDetails?finder=ById;Id={Id},siteNumber={CX_n}` → `ExternalDescriptionStr`).
  `fetch_detail` parses the host + `siteNumber` off the seeded list endpoint, so one seed field drives
  both calls. Routed by the same `_DETAIL_RESOLVERS` map introduced in D-050.
- **Mapping:** `external_id = Id` (the stable requisition id + diff key D-016 + apply-URL path),
  `title = Title`, `location = PrimaryLocation` (already readable, e.g. "Baxley, GA, United States"),
  `updated_at = PostedDate`.
- **Only Southern Company onboarded; Honeywell + Con Edison deferred to curation.** Of the 3 seeded
  Oracle tenants, only Southern resolves to a clean public host now. **Honeywell**'s vanity domain
  `careers.honeywell.com` serves the CE UI but proxies the REST path (302→404); **Con Edison**'s Oracle
  host isn't exposed (careers stay on coned.com). Both were reclassified `oracle_hcm/detected →
  custom/layer2` (the iCIMS Joby/Alaska precedent, D-048) so the "supported `ats_type` ⟹ has a working
  endpoint" seed invariant holds — `active_fetchable_employers` filters only on status + supported ATS,
  so a supported-but-endpointless row would otherwise be selected and fail. They onboard config-only
  (flip `ats_type` back to `oracle_hcm` + add the endpoint) once a canonical host + siteNumber is found.
- **Coverage:** +1 fetchable (Southern Company — grid/power; `detected → verified`), **42 → 43**.
**Why:** Oracle ORC is a high-frequency utility/aerospace ATS; its CE REST API is one clean generic
fetcher that reuses the Workday lazy-detail path, advancing the D-018 coverage tier. Per-tenant host
discovery is curation, not code — the fetcher is the deliverable.

### D-052 · Phase 8: probe platform APIs before the LLM-read tail; Radancy/TalentBrew fetcher · accepted · 2026-06-24
With Tier-B (iCIMS/Workable/SmartRecruiters/Oracle) done, the docs' next item was the generic Layer-2
**LLM-read** fallback for the `custom`/`layer2` tail. A Step-0 reconnaissance pass (live probes) found the
tail is mostly **JS-rendered SPAs or bot-blocked** (United/Southwest = Phenom shells, NextEra = Radancy,
Aurora = React, GridStatus = 403, Mercuria = a marketing page) — the served HTML carries almost no job
content, so a literal "LLM-read-the-page" fetcher would read nothing on the employers that matter, at
recurring token cost. Two decisions (both run through Hayden):
- **Resequence: probe the two big multi-tenant platforms (Phenom, Radancy) for a clean API *before* the
  generic LLM-read fallback.** This applies the iCIMS lesson (D-048) — the visible portal had no JSON but
  the *product* exposed one — and is faithful to D-017 (route to a generic platform fetcher if one fits;
  Layer 2 is for what truly doesn't). It buys deterministic, testable, no-LLM coverage of the high-volume
  airline/utility portals. The generic LLM-read fallback still comes after, for the truly-custom remainder.
- **Radancy first** (Phenom is the next block). Radancy covers 3 grid utilities (NextEra, NRG, National
  Grid) + L3Harris (aviation); grid is the priority/seeded vertical (D-022).

The fetcher (`src/vja/fetchers/radancy.py`, `RadancyFetcher`):
- **Target = the server-rendered search-results endpoint, not the JS landing page.**
  ``GET {endpoint}/search-jobs/results?CurrentPage={n}&RecordsPerPage={N}&SearchType=5`` → an HTML page
  with a ``<table id="searchresults">`` of ``<tr class="data-row">`` jobs (same TalentBrew markup across
  tenants → one generic per-platform fetcher, not a per-company scraper, D-017/D-004). Always HTML
  (`Accept: application/json` still returns HTML), so it's an **HTML-parse fetcher** (the repo's first) —
  one new runtime dep, **`beautifulsoup4`** (pure-Python `html.parser` backend, no lxml/C build).
- **Contract mirrors Workday: list-only + paginate-or-fail + lazy detail.** The grand total comes from the
  table's ``aria-label`` ("Results 1 to 25 **of 288**"); pagination is by ``CurrentPage`` until the
  collected count reaches it; a short tally or an unparseable total is a hard `FetchError` (a truncated or
  mis-parsed scrape must never read as mass closures — the false-closure guard, `docs/08`). The rows carry
  no description, so it's fetched lazily per in-scope survivor via ``fetch_detail`` (the per-job page's
  ``div.jobdescription``), routed by the same `extract._DETAIL_RESOLVERS` map (now 4 entries).
- **Mapping:** ``external_id`` = the ``/job/{slug}/{id}`` **path** (D-016). The detail URL needs the slug —
  the numeric id alone redirects to an error page — and ``fetch_detail`` takes only ``(employer,
  external_id)``, so the path *is* the id (widening that signature would couple fetchers to the db layer,
  an import-linter violation). This is the same **path-as-id shape Workday's ``externalPath`` uses**, and
  carries Workday's same accepted (low) retitle-churn risk. ``apply_url`` = that path made absolute;
  ``location`` from the ``jobLocation`` cell; ``updated_at`` from the ``jobDate`` cell parsed (`%b %d, %Y`)
  to an ISO date (a D-030 freshness win, unlike Workday).
- **Only NextEra onboarded; NRG/National Grid/L3Harris parked.** NextEra `layer2 → verified` (endpoint =
  search base, 288 open at probe). The other three didn't cleanly verify at probe (NRG 200 but different
  results markup; National Grid 403 bot-blocked; L3Harris 301-redirects), so — since wiring `RADANCY` into
  `SUPPORTED_ATS_TYPES` means `active_fetchable_employers` would now *select* any active `radancy` row and
  fail on the missing endpoint — they're parked `status=proposed`/`verification=detected`, kept as
  `radancy` (the Workday P4.2 parked-tenant precedent, D-032), with their probe result in the notes. They
  onboard config-only (flip `active` + add the verified endpoint) once a working search base is curated.
- **Coverage:** +1 fetchable (NextEra — grid/power), **43 → 44** (grid 32 → 33). Adds the Radancy
  *platform*; the parked tenants + Phenom land next.
**Why:** the long tail collapses into a few platforms (D-017), and the probe pass showed the literal
LLM-read step had near-zero reach on the platforms that hold the volume — so cracking Radancy's
server-rendered endpoint is both higher-coverage and stays in the deterministic, no-LLM, testable lane.
The LLM-read fallback is still coming, but for the genuinely structureless remainder, where it earns its cost.

### D-053 · Re-opened postings: reopen the closed row in place, surface as new again · accepted · 2026-06-25
A `vja-run` over the matured corpus crashed 10 employers (Vistra, S&P Global, Jane Street, AES, Xcel,
Fluence, Shell Trading, Yes Energy, Wood Mackenzie, Kraken) with `UNIQUE constraint failed:
postings.employer_id, postings.external_id`, aborting each one's whole transaction (new postings *and*
genuine closures discarded). Root cause: a posting that previously vanished (marked `closed`, never
deleted — D-009) and then **reappears** in a fetch is absent from the open index, so `compute_diff` puts
it in `diff.new`, and `insert_posting` then collides with the still-present closed row. The persist layer
had no resurrection path. Decision:
- **Reopen in place, never re-insert.** `sync_employer` intersects `diff.new` with a new
  `closed_index(employer_id)` (`{external_id: content_hash}` of closed rows); a match routes to
  `reopen_posting` (UPDATE the existing row) instead of `insert_posting`. `diff.py` stays pure set
  arithmetic — the insert-vs-reopen split is a persist-layer concern, like the existing
  still_present→update/bump branch.
- **Surface as new again.** `reopen_posting` resets `first_seen_at = now`, so the role re-enters the
  digest's `new` set (which keys on `first_seen_at > last_sent_at`, D-037) and the dashboard's "new today"
  — a role that's open again is freshly actionable (consistent with the D-024 freshness thesis). Decided
  with Hayden over the quieter "reopen silently" alternative.
- **Cache-aware re-extraction.** When the reappeared body's `content_hash` differs from the stored closed
  row's, `extracted_at`/`extraction_model` are cleared so Layer-2 re-extracts (mirrors `update_changed`);
  an identical body keeps the cached extraction (D-035). `source_updated_at` follows the same non-NULL
  guard as `bump_last_seen`; `location`/`title`/`apply_url`/`raw_payload` refresh from the new L1 read.
- **`reopened` is observability-only.** A `reopened` count rides on `SyncResult`/`RunSummary` and the
  `vja-run`/nightly summary lines; `pipeline_runs.postings_new` keeps counting *true* inserts (no schema
  change — a persisted reopened metric would be a separate column/migration if ever wanted).
**Why:** D-009's "never delete" makes resurrection inevitable as the corpus ages, and a crash that silently
drops an employer's entire diff for the night is exactly the kind of trust-eroding gap the no-mass-close
guard exists to prevent — the fix closes the lifecycle (open → closed → open) the data model always implied.

### D-054 · Phase 9 · 9.1: Postgres path is CI-verified on both dialects · accepted · 2026-06-26
First Phase-9 block (the cloud + multi-user phase, D-047). Makes D-025's "SQLite→Postgres is just a URL
swap + `alembic upgrade`" a *tested* claim rather than an article of faith. **Zero behavior change, no
cutover, no deploy** — purely a portability proof + CI gate.
- **Driver:** `psycopg[binary]>=3.2` added to `[project.dependencies]` (SQLAlchemy-2.0-native
  `postgresql+psycopg://`). SQLite stays the default local + test DB; psycopg is only exercised when the
  URL is Postgres.
- **Test harness:** the single `migrated_engine` fixture (`tests/conftest.py`) honors an optional
  `VJA_TEST_DATABASE_URL`. Unset → today's throwaway `tmp_path` SQLite (unchanged). Set → that Postgres,
  with a per-test `DROP SCHEMA public CASCADE; CREATE SCHEMA public` before `alembic upgrade head` — robust
  isolation against one shared service DB that doesn't depend on every migration having a working
  `downgrade()`. It's the only fixture that builds a DB, so this is the whole harness change.
- **CI:** a new `postgres` job (service `postgres:16`) re-runs the offline default suite with
  `VJA_TEST_DATABASE_URL` set. pytest-only — ruff/mypy/import-linter/`uv lock --check`/frontend are
  dialect-agnostic and already covered by `gates`, so they aren't duplicated.
- **Dialect gaps found:** none. The 315-test suite (which builds its schema via `alembic upgrade head` per
  test, so migrations are exercised too) passed on Postgres on the first run — the Core schema's
  portability choices held: `native_enum=False` VARCHAR+CHECK enums, `UTCDateTime` over
  `DateTime(timezone=True)` (→ `timestamptz`), `sa.JSON`, integer `server_default`s.
**Why:** every later Phase-9 block adds the most security- and PII-sensitive tables (users, sessions,
uploaded résumés). Landing the Postgres CI matrix *first* (cheap, pure-backend, no decisions entangled)
means those tables are born-on-Postgres-verified as they're written — instead of designed on SQLite and
debugged on the live dialect under deploy-deadline pressure during the cutover (9.5). Refines D-025.

### D-055 · Phase 9 · 9.2: auth foundation — Google OAuth + `users` + read-API authz · accepted · 2026-06-26
Second Phase-9 block (D-047), the layer **9.3's behind-login write endpoints depend on**. Builds the
identity/authn/authz layer `docs/11 §3.2` enumerates and `§2` reserved the `(vertical, profile_id)` seam
for. Scope is local plumbing: **no deploy** (9.5) and **no login frontend** (9.4) yet. Three forks, run
through Hayden:
- **Real Google OAuth, exercised locally** (over "machinery now, bind Google at deploy"). Authlib's
  Starlette OIDC client (`server_metadata_url` discovery, `scope=openid email profile`); `/auth/login` →
  Google → `/auth/callback` exchanges the code, reads `sub`/`email`/`name`, and opens a **signed-cookie
  session** (Starlette `SessionMiddleware` + `itsdangerous`, secret = `VJA_SESSION_SECRET`). Routes are
  **inert (503) until `GOOGLE_CLIENT_*` are set**; OIDC discovery is lazy (no network until a login). The
  real Google round-trip is a **manual** check (the `live`-marker philosophy); the default suite mocks the
  token exchange. Hayden provisions the OAuth client (consent screen + Web credentials, localhost redirect
  `http://localhost:8000/auth/callback`); **prod redirect URIs are deferred to 9.5**. New deps: `authlib`,
  `itsdangerous`. (Authlib ships no stubs → a scoped `ignore_missing_imports` at the api boundary.)
- **`users` table + nullable `profiles.user_id` FK** (over "email as the sole join key"). `users` =
  (`id`, `google_sub` unique/nullable, `email` unique/not-null, `name`, `created_at`); PII tier alongside
  profiles/matches/digests (`docs/11 §2`), never denormalized into shared tables. **Identity still anchors
  on email (D-027):** `upsert_user_by_google` matches `google_sub` → adopts an email-only row → inserts,
  and **backfills `profiles.user_id` by email** on first login — so the pre-existing seed profile attaches
  with no data-migration step. `profiles.user_email` is kept, so match/digest/nightly recipient resolution
  is untouched (purely additive). Migration uses `op.batch_alter_table` so the FK lands on **both
  dialects** (SQLite rebuild + Postgres direct); verified on both per D-054.
- **Build the authz layer, defer *hard* enforcement** (over "flip the API to auth-required now"). The read
  API's `_resolve_profile` now takes the current user: **authenticated** → resolves to *that user's*
  profile for the vertical (linked by email), a `profile_id` that isn't theirs → **403**; **unauthenticated**
  → the original single-active default (404/409), keeping the local dashboard usable before there's a login
  UI. `VJA_AUTH_REQUIRED` (default off) is the **enforcement seam**: when on, an unauthenticated read is
  401 — flipped in 9.4/9.5 without re-architecting. A `require_user` dependency is ready for 9.3's writes.
**Why:** 9.3 (résumé upload + signup→backfill) spends LLM tokens and must sit behind a real login, so auth
must be genuinely usable now, not stubbed. Anchoring on the existing email seam (D-027) makes the `users`
addition a backfill, not a rewrite, and deferred enforcement keeps every prior block working while the
machinery lands. **Out of scope (later):** multi-profile-per-user, prod OAuth redirect URIs + session-cookie
hardening (`https_only`/`SameSite`) at deploy (9.5), and abuse/cost guards on the write path (9.3).
**Migration fix (found via the live login):** the `profiles.user_id` batch rebuild crashed on the populated
`vja.db` (DROP `profiles` tripped `matches`'s FK under `PRAGMA foreign_keys=ON`). `migrations/env.py` now runs
on a dedicated engine with **SQLite FKs OFF** (the app keeps them ON) — SQLite's documented ALTER procedure —
pinned by a populated-DB regression test (`test_add_user_id_on_populated_db`). A latent gap the empty-table
fixture couldn't catch; it would have bitten the 9.5 cutover regardless. Refines D-054.

### D-056 · Pre-9.3: digest summarizes closures by company above a threshold · accepted · 2026-06-26
The digest **body** listed each closed role as one bullet. The Phase-8 cash-in run produced a 2-day backlog of
~940 closures (Boeing 241, GE Vernova 147, Airbus 134…), which rendered as a ~940-bullet wall burying the ~66
new roles. Fix is **render-only** (`src/vja/digest/render.py`): **≤ 10 closures enumerate as before; > 10 roll
up by company** — `N roles across C companies:` then the top 10 companies (`• Company — n`, count desc) and
`…and M more companies (P roles)` for the tail. The subject keeps the **true** count (`… N closed`) and the
audit blob (`contents_to_dict`) keeps the **full** closed list — only the human-facing body is summarized.
New/quarantine paths untouched.
**Why:** the kill-criterion requires every digest to carry signal; a wall of dead links trains the reader to
ignore the email, and the nightly would re-send it unattended. Company-level rollup is the right altitude for
closures (you can't apply to a closed role — "which companies shed roles" is the signal), while small days keep
the specific titles. Threshold 10 keeps a normal daily delta detailed and rolls up only backlog days. Body-only
keeps the change tiny and leaves audit / D-037 completeness intact. A pre-req cleanup before 9.3 so the held
digest ships clean.

### D-057 · Phase 9 · 9.3: résumé upload + signup→backfill + cost/abuse guards · accepted · 2026-06-27
Third Phase-9 block (D-047), the layer 9.2 (D-055) built `require_user` for. Adds the product's **first
write path** — a logged-in user uploads a résumé, a profile is created, and the D-039 signup backfill
matches it against the last 5 days of open postings. Because this is the first place a *user action spends
LLM tokens* (docs/11 §3.3), it ships with cost guards. Scope is backend-only: the upload **UI** is 9.4,
prod hardening (encryption-at-rest, captcha, edge rate-limit, verified sending domain) is 9.5. Four forks,
run through Hayden:
- **Résumé formats = text/markdown + text-based PDF (`pypdf`)** (over text-only, or full OCR now). New leaf
  module `src/vja/resume.py` (`extract_resume_text`, the D-033 adapter, imports no `vja` module). A
  scanned/image PDF has no text layer → rejected (422); OCR / Claude native-PDF input is a later add. All
  failure modes raise `ResumeError`. **PII: the text is never logged** (docs/11 §3.1). New deps `pypdf` +
  `python-multipart` (FastAPI form parsing).
- **Backfill runs in the background** (over inline-synchronous, or defer-to-nightly). `POST /api/profiles`
  returns **202 + `profile_id`** immediately; `run_backfill` runs as a FastAPI `BackgroundTask` (a sync
  callable → Starlette threadpool, so it doesn't block the event loop). Matches land on the existing
  dashboard as they complete. The work is already a plain callable, so the 9.5 cloud cutover swaps it for a
  Cloud Run Job (D-031) with no rework.
- **Cost guards = per-backfill cap + global daily ceiling** (skip per-user cooldown; defer captcha/email-
  verify/edge rate-limit to 9.5, since OAuth already bounds abuse to real Google accounts). The cap
  (`VJA_BACKFILL_MAX_POSTINGS`, default 100) slices the surviving candidate set inside `run_backfill` so one
  signup can't run away; **nightly stays uncapped** (`_match_profile(max_postings=None)`, pinned by the
  unchanged `test_matching_run.py`). The ceiling (`VJA_DAILY_LLM_BUDGET_USD`, default $5) is checked
  *before* a backfill is scheduled → **429**. With no per-match cost ledger (only `pipeline_runs.llm_cost_usd`,
  which the backfill doesn't write), spend is **estimated** as `count_matches_since(midnight) ×
  _NOMINAL_MATCH_USD` (~$0.01) — a proxy good enough to backstop the bill without a schema change.
- **Endpoint = `POST /api/profiles` (multipart), no status endpoint** (over adding pollable backfill state).
  Behind `require_user` (401 without a session). Resolves the user from the session, pulls
  `domain_vocabulary` from the vertical config (404 on an unknown vertical), and `upsert_profile` now stamps
  `user_id` at creation (the D-055 link applied at upload, not only at login; CLI path unchanged, still
  NULL→linked-by-email). A status endpoint would need persisted backfill state (schema churn) for little
  gain now — the 9.4 frontend can watch matches appear via `/api/postings`; add it later only if needed.
**Why:** the upload→backfill flow is the first user-driven LLM spend, so it must sit behind a real login
(9.2) *and* behind a cost ceiling before any public signup. Background execution keeps the upload responsive;
the two guards bound both per-signup and total daily cost without new infrastructure. **Out of scope
(later):** the upload/login UI (9.4); encryption-at-rest, deletion/DSR, captcha, edge rate-limiting,
verified sending domain, prod OAuth redirect URIs (9.5); per-user cooldown, a real per-match cost ledger,
and a backfill-status endpoint.

### D-058 · Phase 9 · 9.4: multi-user frontend (Rolefeed) + product naming · accepted · 2026-06-29
Fourth Phase-9 block (D-047): the UI that makes the 9.2 auth and 9.3 write path reachable. **No backend
code changes** — every endpoint (`/auth/login|callback|logout`, `/api/me`, `POST /api/profiles`) already
exists and CORS already allows credentials (D-055/D-057); 9.4 is purely the `frontend/` SPA wiring the user
flow: sign in → upload a résumé → see *your* matches. **Product name: Rolefeed** — the wordmark, page title,
and package name switch from the internal `vja` to Rolefeed (the codebase/CLI stay `vja`; this is a
user-facing brand only). Decisions, run through Hayden:
- **Routed pages via `react-router-dom`** (over conditional rendering in one component): `/` dashboard,
  `/login`, `/upload`. `App.tsx` becomes the shell (brand + auth-aware nav) + `<Routes>`; the old App body
  is extracted verbatim to `pages/Dashboard.tsx` (behaviour unchanged). Adds the SPA's first dependency.
- **`VJA_AUTH_REQUIRED` stays off in 9.4** (over flipping it on now): the dashboard remains reachable
  anonymously (single-active default profile), login only gates the `/upload` write path (a soft client
  redirect; the POST is hard-guarded by `require_user` server-side). Existing API tests stay green; the hard
  gate + prod cookie/redirect hardening flip together at the 9.5 deploy.
- **Credentialed fetches** (`credentials: "include"` on every call): the signed-cookie session rides along,
  so a logged-in user resolves to their own profile server-side (`_resolve_profile`, D-055) — the seam 9.2
  built. `/api/me` 401 ⇒ "logged out" (null), not an error.
- **Optimistic upload feedback** (honours D-057's no-status-endpoint): on 202 the form shows "résumé
  received (v{n}) — matching runs in the background" + a link back to the dashboard, which re-queries
  `/api/postings` on navigation. No polling, no new endpoint, no schema change. The 413/422/429/404 guard
  responses surface inline via a typed `ApiError` carrying the server `detail`.
- **Auth module split for clean Fast-Refresh**: `auth/useAuth.ts` (context + hook, no component) +
  `auth/AuthProvider.tsx` (the provider) — so no file mixes a component with a hook export.
**Why:** get a real user in front of the product (D-047's reason for pulling Phase 9 ahead of the discovery
agent) with the smallest reviewable surface, reusing the finished backend untouched. Routing leaves room for
the next product views without a rewrite; deferring the auth gate keeps local dev frictionless and the
review small. **Out of scope (later, 9.5):** flipping `VJA_AUTH_REQUIRED` on; prod OAuth redirect URIs +
cookie hardening; deploy; and a deep-link/hard-refresh fallback (prod `StaticFiles(html=True)` 404s a hard
reload of `/upload`|`/login` — client-side nav is fine; needs a catch-all → `index.html` at the deploy).

### D-059 · Phase 9 · 9.5a: deploy-readiness app hardening · accepted · 2026-06-29
First block of the Phase-9.5 cutover (plan of record: `docs/12-cloud-deploy-plan.md`). **Code-only, no
infra** — closes the app-level seams that a TLS-terminating proxy (Cloud Run) + an enforced auth gate
expose, so 9.5b–d are pure packaging + ops. Every prod behavior is **env-gated**; local dev defaults are
unchanged. The seams (all in `src/vja/api/`, surfaced by this session's loose-ends audit):
- **Session cookie hardening** (`auth.cookie_https_only`/`session_max_age` → `SessionMiddleware`): `Secure`
  in prod via `VJA_COOKIE_SECURE` (off by default so dev over http://localhost works), `SameSite=Lax`
  **always** (Strict breaks Google's top-level OAuth redirect), `max_age` from `VJA_SESSION_MAX_AGE`
  (default 14 days).
- **HTTPS OAuth redirect_uri** (`auth.oauth_redirect_uri`): prefers an explicit `VJA_PUBLIC_BASE_URL` so the
  callback is `https://…` behind the proxy — `request.url_for` would yield `http://` and trip Google's
  `redirect_uri_mismatch`. Belt-and-suspenders: `uvicorn.run(..., proxy_headers=True,
  forwarded_allow_ips="*")` honours `X-Forwarded-Proto` for the fallback path.
- **SPA deep-link catch-all** (`_mount_spa`): replaces `StaticFiles(html=True)` with explicit `/assets` +
  a trailing `/{full_path:path}` route returning `index.html` for client routes (so a hard-refresh of
  `/upload`|`/login` doesn't 404), serving real files verbatim and **404ing unknown `/api`·`/auth`** rather
  than masking them. Gated on a real `index.html` (a stale/empty `dist/` is skipped — found one locally).
- **Container bind** (`_parse_args`): `--host`/`--port` default from `VJA_API_HOST`/`PORT` so the image
  honours Cloud Run's injected `$PORT` and binds `0.0.0.0`; local stays 127.0.0.1:8000; flags still override.
- **CORS**: already env-driven (`VJA_CORS_ORIGINS`); prod is same-origin so it's unused — documented only.
**Why:** discover these now as testable code (the audit's point) rather than at deploy as a debugging
session; keep dev frictionless by env-gating every prod change. **Tests:** `tests/unit/test_api_helpers.py`
(+8: cookie flag default/on, max_age default/override, redirect-uri prefers base / falls back to url_for,
parse-args env + flag-override) and `tests/integration/test_serving.py` (+4 → really 3 funcs: index/assets/
deeplink served, /api·/auth not masked, no mount without a real build). Full gate green, 367 pytest (+12).
**Out of scope (later 9.5 blocks):** the Dockerfile (9.5b); provisioning + the actual flips of
`VJA_AUTH_REQUIRED`/`VJA_COOKIE_SECURE`/`VJA_PUBLIC_BASE_URL` + prod OAuth URIs (9.5c/d).

### D-060 · Phase 9 · 9.5b: containerization (one image, two run targets) · accepted · 2026-06-29
Second 9.5 block (plan: `docs/12`). Packages the app as a single multi-stage image so 9.5c/d are pure ops.
- **Multi-stage `Dockerfile`** (repo root): stage `web` (`node:24-bookworm-slim` — **Debian/glibc, not
  alpine**, to dodge the musl `@rollup/rollup-linux-x64-musl` optional-binary build break; matches local
  node v24.7) builds the SPA; runtime stage (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`) installs the
  package and copies `frontend/dist` in.
- **Non-editable install** (`uv sync --frozen --no-dev --no-editable`, two layers — deps then project — for
  cache efficiency): the running code is an immutable installed wheel, not a `/app/src` `.pth` link
  (editable-in-prod is an anti-pattern).
- **`VJA_FRONTEND_DIST` env** (new helper `app.frontend_dist_dir()`): the non-editable install moves the
  package out of the repo layout that `Path(__file__).parents[3]/frontend/dist` assumed, so the dist dir
  becomes explicit config (set to `/app/frontend/dist` in the image), defaulting to the repo layout for
  dev/CI. This — not editable-install — is what *unlocks* the clean install; without it the path silently
  breaks. (~5 lines + 1 unit test; the 9.5a serving tests now drive via the env, not a removed module const.)
- **One image, two run targets** (D-031): default `CMD` is `vja-api --host 0.0.0.0` (Cloud Run service,
  API + SPA same-origin); the Cloud Run **Job** overrides the entrypoint to `vja-nightly` — no second build.
- **Runtime data baked in** (`config/`, `migrations/` + `alembic.ini`, `data/seed/`): alembic needs them
  adjacent for 9.5d's `alembic upgrade`; nightly/import needs config + employer seed. **No secrets / no
  `VJA_DATABASE_URL`** in the image — all runtime env (→ Secret Manager at 9.5c).
- **`.dockerignore`** keeps the local SQLite (`data/*.db`), `node_modules`, the host `frontend/dist`
  (rebuilt in-image), `.git`, caches, `tests`/`docs` out of the context.
**Why:** a reproducible, immutable artifact buildable/mergeable before any GCP/Neon/domain exists; the
explicit dist path removes the layout-coupling footgun a proper prod install would otherwise expose.
**Verified:** full Python gate green, **369 pytest** (+2); `docker build` clean; local prod-parity smoke —
`/api/health` ok, `/` + `/upload` (catch-all) return the Rolefeed SPA, `/assets/*` 200, unknown `/api` 404,
binds `0.0.0.0:8000`; both `vja-api` + `vja-nightly` entrypoints present (601 MB image). **Out of scope:**
provisioning (9.5c) + deploy/cutover/flips (9.5d).

### D-061 · Phase 9 · 9.5c: cloud provisioning standup (locked values) · accepted · 2026-06-30
Third 9.5 block (plan: `docs/12`). Provision the cloud resources the 9.5d cutover deploys *into* — no app
code, no deploy, no go-live flips. Runbook: `deploy/gcp/README.md`. Concrete, re-litigable values now locked
as fact:
- **Domain:** `role-feed.com` (Cloudflare Registrar; DNS stays Cloudflare). **Hyphenated** — the `docs/12`
  table had assumed `<rolefeed>.com`; the literal differs everywhere (OAuth redirect, `VJA_PUBLIC_BASE_URL`,
  `VJA_DIGEST_FROM`, cookie domain).
- **GCP project:** `role-feed-prod` (number 850723734041), billing linked, APIs enabled (run,
  artifactregistry, cloudscheduler, secretmanager — no Cloud SQL, Postgres is Neon).
- **Region:** GCP `us-central1`; **Neon** Postgres in **AWS us-east-2 (Ohio)**, nearest. Fresh DB, no
  SQLite carryover (D-025); `VJA_DATABASE_URL` stored as the **pooled** endpoint with the SQLAlchemy
  **`postgresql+psycopg://`** scheme (the Neon dashboard hands out bare `postgresql://` — the `+psycopg`
  rewrite is mandatory or the app reaches for the absent psycopg2).
- **Secret Manager:** all 8 prod secrets loaded (the D-025/docs/12 set). **Non-secret** prod env
  (`VJA_AUTH_REQUIRED=1`, `VJA_COOKIE_SECURE=1`, `VJA_PUBLIC_BASE_URL=https://role-feed.com`,
  `VJA_FRONTEND_DIST=/app/frontend/dist`) are plain Cloud Run vars, applied at 9.5d.
- **OAuth:** web client created **in `role-feed-prod`** (consent screen External/Testing + test users),
  redirect `https://role-feed.com/auth/callback`; the `*.run.app` fallback URI added at 9.5d once the
  service URL exists. (An initial client mistakenly made under another project was discarded and re-created
  here — credentials are project-portable but the consent screen/test-users/lifecycle belong in prod.)
- **Resend:** `role-feed.com` verified (SPF/DKIM in Cloudflare); `digest@role-feed.com` sends without a
  mailbox (send-only; replies bounce — acceptable for a no-reply digest).
- **Artifact Registry:** Docker repo `rolefeed` in `us-central1` (the 9.5d push target).
**Why:** record the standup as fact so 9.5d (and any reset session) treats the domain/region/project/URL-
scheme as settled, not re-litigable; a standalone ADR keeps the 9.5d cutover ADR scoped to go-live.
**Verified:** `gcloud` reads confirm project+billing, 4 APIs, AR repo, all 8 secrets with enabled versions,
OAuth client (secret versions @ v2 = the re-created prod client), Neon URL stored pooled + `+psycopg`. The
**DB connect from a laptop is blocked by local-network port-5432 filtering** — irrelevant to prod (Cloud Run
reaches Neon over the cloud backbone); the authoritative connect/`alembic upgrade head` runs at 9.5d via a
Cloud Run Job exec. **Out of scope:** image push, Cloud Run deploy, custom-domain mapping, schema migration,
baseline run, the `VJA_AUTH_REQUIRED`/`VJA_COOKIE_SECURE` flips, `/security-review` — all 9.5d.

### D-062 · Phase 9 · 9.5d-prep: serverless-PG engine hardening + cutover runbook · accepted · 2026-06-30
Repo-side prep for the 9.5d cutover (branch `feat/9.5d-prep`), ahead of the ops-only go-live. Three things:
- **DB engine resilience for Neon (code).** `get_engine` (`src/vja/db/engine.py`) now builds every engine with
  **`pool_pre_ping=True`** (all dialects — a cheap liveness check before a pooled connection is handed out) and,
  for **non-SQLite** URLs only, **`pool_recycle=1800`s** (`POOL_RECYCLE_SECONDS`). **Why:** Neon's free tier
  autosuspends on idle and can drop pooled connections server-side; without pre-ping the first query after a
  suspend raises `OperationalError`, and recycle retires connections before Neon's timeout does. SQLite's
  connection is local, so recycle stays at SQLAlchemy's `-1` default there. Pinned by unit tests asserting the
  pool kwargs on both dialects (offline — `create_engine` is lazy). Pool *sizing* left at defaults (Neon's
  pooled endpoint multiplexes via pgbouncer; don't over-tune ahead of need).
- **9.5d cutover runbook** `deploy/gcp/CUTOVER.md` — the executable analogue of the 9.5c `README.md`.
  **Corrects D-061's carried assumption:** Hayden's laptop **can** reach Neon (a `create_engine().connect()`
  reach-test against the pooled URL returned `neon ok`), so `alembic upgrade head` + the baseline seed run
  **locally from his shell**, not via a Cloud Run Job exec. Adds a **staged `*.run.app` smoke (incl. a login
  round-trip) before domain-mapping and before the auth flip**, the `--platform linux/amd64` build gotcha
  (arm64 laptop → amd64 Cloud Run), the runtime-SA `secretAccessor` grant, and a `update-traffic` rollback note.
- **Post-launch change management** documented as `docs/11` §5: **Path A** (data — employers/profiles → DB via
  `vja-import-employers`/upload, **no redeploy**) vs **Path B** (config/code — `config/verticals/*.yaml` +
  fetchers are baked into the image, **rebuild+deploy**). Recommends a merge-triggered auto-deploy as a
  post-launch "9.6" fast-follow; flags (not now) moving vertical config out of the image if churn ever hurts.
**Why:** make 9.5d a scripted, safe-not-sorry execution and answer "how do we ship changes after launch" (2 new
verticals + expansion + the discovery agent) before go-live, without doing any irreversible cloud ops in-session.
**Verified:** full Python gate green (ruff/mypy/import-linter/`uv lock --check`/pytest on SQLite + CI Postgres);
new engine tests pass. **Out of scope (still 9.5d):** every cloud op in `CUTOVER.md` — build/push/deploy/migrate/
seed/flip/`/security-review` — run by Hayden with his own gcloud/console auth. **Status:** merged pending (Hayden
commits + PRs the branch).

### D-063 · Phase 9 · 9.5d: vertical config dir resolves via `VJA_VERTICALS_DIR` in the container · accepted · 2026-07-02
Found live during the 9.5d cutover: `vja-nightly` executions completed "ok" but did **zero Layer-2 work**
(`extracted=0 matched=0 digests=none $0`), reproducibly, while the same code ran fine locally night after night.
**Root cause:** `vja.verticals._CONFIG_DIR` was `Path(__file__).resolve().parents[2] / "config" / "verticals"`,
which only lands on the repo root under the **src/editable** layout. The image installs the package
**`--no-editable`** (into `.venv/.../site-packages`, an immutable artifact — deliberate), so in the container
`parents[2]` resolves to `…/python3.12/config/verticals` (nonexistent). `available_verticals()` returned `[]`,
so the nightly's `for vertical in available_verticals()` loop never iterated — no extraction, no matching, no
digest — and the failure was **silent** (an empty config dir is not an error). Proven by running the deployed
image directly: default path → `[]`; the copied `/app/config/verticals` → both verticals load.
**Decision:** honor a **`VJA_VERTICALS_DIR`** env override in `verticals.py` (env wins, else the repo-layout
default), and set it in the Dockerfile to **`/app/config/verticals`** (where `COPY config` lands). This is the
**same fix already used for the SPA** (`VJA_FRONTEND_DIST`, D-060) — the identical `--no-editable` path problem;
the config path simply never got the same treatment. **Rejected:** switching the image to an editable install
(defeats the immutable-artifact intent) and shipping configs as wheel package-data (config is external data, not
code). **Verified:** +1 regression test (`test_config_dir_honors_env_override`); ruff/mypy clean; 372 pytest
green. Rebuilt image `b2a74fa` redeployed (service + Job, Job also given `--task-timeout=7200`/`--max-retries=1`
for the real backlog run's duration); execution `vja-nightly-295wd` confirmed hitting `api.anthropic.com` in the
extraction phase. **Follow-up:** consider auditing for any other `Path(__file__).parents[…]` repo-relative
resolutions that assume the src layout (the two known — frontend + verticals — are now both env-guarded).
**Status:** accepted; **merged to `main` via PR #49** (`329ff1f`) — deployed `b2a74fa` matches the default branch.

### D-064 · Phase 9 · One vertical per user — made explicit (policy always held) · accepted · 2026-07-06
**A user belongs to exactly one vertical.** This has been the product policy since inception (a user is matched
against one bounded employer universe — the moat), but it was **never written down**, and the frontend drifted
into treating "vertical" as a **global, cross-user picker**: `active_verticals()` (`src/vja/db/profiles.py:131`)
returns every vertical with any active profile, and `Dashboard.tsx` defaults to the sorted-first
(`aviation_software`) regardless of who is logged in — so a grid user lands on aviation and 404s. **Decision:**
one **active** profile per user, in one vertical, chosen **once at signup** and **immutable** — changing
verticals is a manual/support action, **out of scope for v1** (no switch UI). The dashboard shows *that user's*
vertical; there is **no cross-user vertical picker**. Enforcement: `/api/me` drives per-user routing and the
write path (`POST /api/profiles`) rejects a second vertical for a user who already has one. **Supersedes** the
implied-multi-vertical reading of D-042's "`GET /api/verticals` drives the picker" — that endpoint stays for
admin/internal use but no longer drives per-user routing. **Why:** it's the product's actual model; the global
picker was a documentation/communication lapse, not a design change. **Status:** **done** — enforced at
`POST /api/profiles` (409 on a second vertical; same-vertical re-upload stays an idempotent résumé update) and
routed per-user via `/api/me` → `active_profile_for_user`; the global `active_verticals()` was removed and
`GET /api/verticals` repointed to config-driven `available_verticals()` (onboarding picker only). Data cleanup
(B-4, deactivate Hayden's aviation seed profile) is a prod write pending at deploy. (D-065)

### D-065 · Phase 9 · Onboarding / auth-UX overhaul — target flow · accepted · 2026-07-06
The deployed flow is broken for a fresh account: logged out, `/` renders a **401 as an error string** (no login
landing); after login, the **global-vertical picker 404s** (D-064); the vertical chosen at upload is ignored;
there is **no onboarding gate** routing a profile-less user to upload. **Decision — target flow** (Hayden,
2026-07-06): (1) a **static landing page** (minimal placeholder + login CTA) — the dashboard is **never rendered
logged-out**; (2) **Google-auth signup**; (3) **one page: pick vertical + upload résumé**; (4) **route to their
dashboard** — *cleaned/all* renders immediately, *matched* shows a **loading indicator** resolved by a
**bounded client-side poll** (no backend push/status endpoint — honors D-057), timing out to *"full results
after tonight's run."* Backend adds **`GET /api/me`** (user + their single vertical) and **one-vertical
enforcement**; frontend adds **route guards** (unauth→landing/login, authed+no-profile→onboarding,
authed+profile→their dashboard) and **`prompt="select_account"`** on `/auth/login` (Google was silently reusing
one session). **Why:** the current UX "does not work" for beta users — this is a **launch blocker**, ahead of
inviting them. **Status:** **done** — backend: `/api/me` returns `{user, profile|null}`, one-vertical 409,
`prompt="select_account"`. Frontend: `App.tsx` route guards off `useAuth()` (Landing / `/login` / `/onboarding`
/ `/dashboard` / `/upload`-locked), `Dashboard` takes its vertical from the profile (the 404 fix) + the matched
poll, onboarding refreshes `/api/me` then routes to the dashboard. Green: Python 379 + frontend eslint/tsc/
vitest 45. Ships via `ship.sh` (D-066); then re-run the fresh-account walkthrough before beta invites. (D-064)

### D-066 · Phase 9 · Thin scripted deploy before the onboarding block; full CI/CD deferred · accepted · 2026-07-06
To ship the onboarding fix (D-065) **reliably today** without a CI/CD detour: a **single idempotent deploy
script** (`deploy/gcp/ship.sh` or a Make target) that captures the manual cutover steps — `docker build
--platform linux/amd64` → push → `gcloud run deploy` (service) → `gcloud run jobs update` (nightly, same image)
→ health smoke — so no deploy forgets the platform flag, a secret mount, or the Job update. **Rejected for now:**
full merge-triggered CI/CD (the `docs/11` §5 "9.6" auto-deploy) — a bigger project that would *delay* today's
ship; deferred until iteration churn justifies it. **Sequence:** ship-script phase (A) → onboarding-fix phase
(B), both `docs/13`. **Why:** de-risk the many deploys of the hardening week without a multi-day infra detour.
**Status:** **done** — `deploy/gcp/ship.sh` shipped (build → push → deploy service → update Job → `/api/health`
+ anon-401 auth-guard smoke; captures prior revision → prints the `update-traffic` rollback; preserves the guard
env vars, never sets them). Redeploy-only (schema/seed/domain stay manual, CUTOVER §3). Docs: `deploy/gcp/README.md`
"Redeploying (`ship.sh`)". Full CI/CD ("9.6") still deferred.

### D-067 · Phase 9 · 9.5d go-live complete; "green mapping / dead TLS" was a corporate-network block · accepted · 2026-07-06
9.5d executed end-to-end: image built/pushed, `alembic upgrade head` on Neon, baseline seed (**9,773 postings /
2 profiles**), Cloud Run service deployed, `*.run.app` smoke + Google login, custom domain **`role-feed.com`**
mapped (cert green), nightly **Job + Scheduler** (`0 6 * * *` America/Chicago), and the **prod guards flipped**:
`VJA_AUTH_REQUIRED=1`, `VJA_COOKIE_SECURE=1`, `VJA_PUBLIC_BASE_URL=https://role-feed.com` (verified: anon
`/api/postings` → 401). **Operational lesson (don't re-panic):** `role-feed.com` reset TLS **right after the
ClientHello** from the office network for ~an hour, while the Cloud Run mapping read `Ready` +
`CertificateProvisioned` and DNS was correct (DNS-only, Google anycast IPs). Cause was **corporate wifi blocking
newly-registered domains** (a common firewall category), **not** Cloud Run — proven by success over a phone
hotspot (and it typically ages out ~30 days post-registration). A delete+recreate of the mapping was a red
herring but harmless. **Mitigation:** Hayden uses hotspot or has IT allowlist the domain; beta users on their
own networks are unaffected. **Remaining 9.5d closeout:** real email E2E + `/security-review`. **Caveat:** the
*cloud cutover* is done, but the **product is not yet usable by beta users** — the onboarding UX (D-065) is a
blocker. **Status:** accepted; go-live infra done, closeout + onboarding tracked in `docs/13`.
**Closeout update (2026-07-08):** both closeout items **done** — email E2E verified (digests sending from the
verified `digest@role-feed.com`) and `/security-review` complete; the D-065 onboarding blocker is fixed and
real private users are signed up. Go-live is fully closed; the active work is beta hardening (D-072).

### D-068 · Phase 9.6 · Merge-triggered CI/CD to Cloud Run (WIF, auto-deploy, migrations stay manual) · accepted · 2026-07-06
Replaces the manual `ship.sh` invocation (D-066) with **auto-deploy on merge**: the `deploy` job in
`.github/workflows/ci.yml` runs after every CI gate is green (`needs: [gates, postgres, frontend, secrets]`),
only on push-to-`main` or `workflow_dispatch` (never PRs), and rolls the new image onto the `rolefeed` service +
`vja-nightly` Job. **Auth = Workload Identity Federation** (keyless OIDC; a `github-deployer` SA impersonated by
the repo's OIDC identity, restricted by an `attribute.repository` condition) — **no SA key in the repo**; the two
identifiers (`GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA`) are repo **variables**, not secrets. **The job execs `ship.sh
--force`, not a re-implementation** — one code path, so the proven secret/SA/`--allow-unauthenticated`/no-env-var
(guards-preserved) config lives in exactly one place and can't drift. `ship.sh` gained an **env-gated
`ROLLBACK_ON_SMOKE_FAIL=1`** (CD sets it): a failed `/api/health`-or-anon-401 smoke auto-shifts traffic back to
the prior revision before failing (deploy sends 100% traffic to the new revision, so a bad one is already live);
default 0 keeps the manual behavior (print + exit). **Migrations stay manual** (D-025/CUTOVER §3): CD deploys
**code only** — a schema-changing PR must run `alembic upgrade head` on Neon **before merge**, or the deploy ships
code ahead of its schema (documented ordering rule; a `workflow_dispatch` migration workflow is a future
convenience, not built). **Why:** close the deploy loop for the beta-hardening week — shipping a fix becomes
"merge the PR," not "run a script from a machine with gcloud creds" — without a long infra detour or the risk of
auto-applying schema changes to prod. Chosen over: a SA JSON key (long-lived credential, rotation burden,
bigger blast radius); a manual-approval `environment` gate (safer but defeats CD for a solo dev — the smoke +
auto-rollback + `ship.sh` break-glass are the safety net instead); a separate `deploy.yml` on `workflow_run`
(fragile default-branch/checkout semantics vs a clean `needs` edge in one workflow). **Status:** code + docs
shipped on `feat/9.6-cicd`; the one-time WIF provisioning + repo variables + first `workflow_dispatch` run are
Hayden-run (needs cloud creds — the DoD, per `deploy/gcp/README.md` §"CI/CD"). `ship.sh` (D-066) stays the manual
break-glass. Supersedes the "9.6 deferred" note in D-066.

### D-069 · Phase 5.x · LLM cost Block 1 — real token metering + Sonnet effort=medium (measure first) · accepted · 2026-07-07
Two signups cost $6/morning; the Anthropic console showed **~10M input : <1M output (input-bound ~10:1)** with
only **~7% cache hit**. Reading the code: **extraction** (Haiku) sends the full, unique-per-posting job
description → **inherently uncacheable** (the input bulk; the lever is the Batch API, not caching), and its
system prompt wasn't even marked cacheable; **matching** (Sonnet) *is* cache-wired correctly but ran at the
API-default **`high` effort** (thinking bills as output). And spend was metered only by a **`$0.01`-per-item
proxy** (`match._NOMINAL_MATCH_USD`) — no real token accounting, so we were optimizing blind. **Decision: stage
it, measure first.** Block 1 (this ADR): (1) **real per-call token accounting** — a `TokenUsage` value
(`models.py`: input/output/cache_read/cache_write, `from_response` + cache-aware `cost()` + `cache_hit_rate`)
returned by `extract_posting`/`match_posting`, summed through the run summaries + `Layer2Summary`, **persisted to
four new `pipeline_runs` columns** (`input_tokens`/`output_tokens`/`cache_read_tokens`/`cache_write_tokens`;
additive Alembic migration, born-on-Postgres-verified per D-054), and logged as a per-stage nightly line with the
matching cache-hit %; (2) **`effort=medium`** on the Sonnet match call, **env-overridable via `VJA_MATCH_EFFORT`**
(mirrors the D-057 backfill knobs) so `low` can be A/B'd in prod without a redeploy — **eval-gated (D-020):** ship
the lowest effort that still passes `tests/eval/test_match_eval.py`; (3) extraction system prompt wrapped in
`cache_control` (**expected no-op** — Haiku's 4096-token cacheable floor exceeds the short prompt — kept as the
correct pattern; the meter now shows whether it fires). **Why:** the meter is the point — it makes
extraction-vs-matching and cached-vs-uncached spend visible each night (honouring the standing "meter LLM spend
from day one" rule the proxy didn't), and it's what sizes/justifies Block 2. **Non-goal → Block 2 (separate):**
**Batch API** (50% off extraction + matching) — the real structural cut, but it restructures the nightly's
submit→poll→collect flow, so it waits for Block 1's real numbers (incl. whether the nightly re-extracts unchanged
postings — a possible `content_hash`-churn bug the meter would expose). Caching is already optimal; "better
caching" is a dead end for the uncacheable input. **Status:** code + docs shipped on
`feat/llm-cost-instrumentation`; the eval sweep (medium vs low) + the post-deploy nightly read of the token
columns are Hayden-run (need `ANTHROPIC_API_KEY` / prod). Supersedes the D-036 "adaptive/high, $0.01 proxy" cost
posture.

### D-070 · Phase 10.1 · Layer-3 discovery agent — thin core (research → validate-by-fetch → `proposed`) · accepted · 2026-07-07
Built the first slice of Phase 10 (the last roadmap item; D-047 demoted it to "shell + formatting around an Opus
deep-web-search that writes `proposed` employer rows"). **Four decisions, run through Hayden in plan mode:**
(1) **thin core first** — one PR: discover → resolve ATS → write `proposed` rows behind `vja-discover`; NO weekly
scheduling, NO approve/reject UI (both → block 10.2); (2) **Anthropic web tools** — Claude Opus 4.8 with the
server-side `web_search_20260209` + `web_fetch_20260209` (no new vendor/key, stays inside the existing SDK
dependency); (3) **admin CLI** as the eventual review surface (not the user-facing Rolefeed SPA); the approve
CLI itself is 10.2, this block only *writes* + prints a summary; (4) **validate by actually fetching** — a
`proposed` row is high-confidence only if the matching registry fetcher actually returns postings. **Shape:** one
new top-tier module `src/vja/discover.py`, two cleanly separated stages — Stage 1 (LLM) runs an agentic
`web_search`/`web_fetch` research loop (bounded by `web_search` `max_uses` + `_MAX_CONTINUATIONS`, handling
`pause_turn`), then a toolless `messages.parse` turn structures the report into `list[CandidateEmployer]`; Stage 2
(deterministic, LLM-free) dedups against the existing universe (normalized name) and validates each candidate by
building an `Employer` from the guess and running `registry.get_fetcher(ats).fetch()` (D-017 reuse) — fetchable+≥1
posting → `proposed`/`detected`, else → `proposed`/`unknown`/`layer2` for manual triage, guess kept in `notes`.
All rows `source=agent_discovered`, `status=proposed`, idempotent on `UNIQUE(vertical, name)` — **no migration**
(the schema already had these enum values, and only `active` is fetched nightly, so proposals sit inert until
approved). **Cost discipline (D-005):** weekly + bounded by design; spend metered with the Block-1 `TokenUsage`
(D-069) at Opus rates, printed per run; effort defaults to `medium` (env-overridable). **Why thin:** prove the
loop produces good proposals before wiring the scheduler/review surface; the literal LLM-read tail (D-052) showed
"measure the reach first" pays off. **Non-goals → block 10.2:** weekly scheduling, the `vja-review` approve/reject
CLI (`list_proposed`/`set_employer_status`), auto-approval, a proposal-precision eval, discovery of non-employer
`sources`. **Status:** code + docs + 14 offline tests on `feat/phase10-discovery-agent`; the live `vja-discover`
smoke (needs `ANTHROPIC_API_KEY`) is Hayden-run.

### D-071 · Phase 10.2 · Layer-3 review surface — `vja-review` approve/reject CLI + ready-but-off weekly schedule · accepted · 2026-07-08
The human gate that promotes D-070's `proposed` employers into live coverage (only `active` employers are fetched
nightly, so proposals are inert without it). **Three decisions, run through Hayden in plan mode:** (1) **Scheduling
= ready-but-OFF** — build + test the review CLI now; ship the weekly schedule as a *documented, disabled* launchd
template (`com.vja.discover.plist.template`, not auto-installed) + a Cloud Scheduler runbook (CUTOVER §8b, not
created). Discovery stays a manual `vja-discover` until its live per-run cost is measured; the trigger is swappable
config, not code (D-031). (2) **Approve → `active` for fetchable, `approved` for layer2.** A proposal whose
`ats_type ∈ SUPPORTED_ATS_TYPES` → `active` (fetched next nightly); a no-fetcher (unknown/layer2) proposal →
`approved` and **parked** with a printed notice — finally giving the `approved` enum value a real job
(vetted-but-not-fetchable). (3) **Reject → `retired`** (never deleted; mirrors D-009). **Fetchability is keyed on
`SUPPORTED_ATS_TYPES`, not `verification`** — the exact predicate the nightly fetch uses, so hand-fixing a row's
`ats_type` to a supported one and approving it correctly activates it (the manual-resolution path, free).
**Parked-safety is structural:** `active_fetchable_employers` filters on both `status=active` AND a supported ATS,
so an `approved`/layer2 row *physically can't* be fetched — no log guard needed; `vja-review list --status approved`
is the flag. **Shape:** new top-tier module `src/vja/review.py` (`approve_employer`/`reject_employer`/`ReviewOutcome`
+ argparse `list`/`approve`/`reject`, entry point `vja-review`, same import-linter layer as `discover`); DB
primitives `list_employers_by_status`/`get_employer_by_id`/`set_employer_status` + an `EmployerListing` read shape in
`db/employers.py`. **No migration** (reuses existing `EmployerStatus` values). **Non-goals → later:** auto-approval,
a proposal-precision eval (needs a real sample), non-employer `sources` review, and actually *enabling* the weekly
schedule. **Status:** code + docs + 8 offline tests (403 total) on `feat/phase10-discovery-agent`; the live
`vja-discover` → `vja-review` CLI walkthrough is Hayden-run. References D-070, D-047, D-031, D-017, D-009, D-005.

### D-072 · Beta hardening · Scope of the pre-broad-invite week (six one-day items) · accepted · 2026-07-08
Go-live is fully closed (D-067 + closeout done) and real private users are signed up, so the launch blockers
are cleared — this decision scopes the **beta-hardening** week that makes the beta *good* before broader
invites. **Reconciled Hayden's plan against the docs' scattered "hardening" notes** (which had drifted:
CLAUDE.md still listed 9.6 CI/CD as "NEXT" though D-068 shipped it, and listed email E2E + `/security-review`
as open closeout though both are done). **Scope = six items, one day each** (verify each sound before the
next), plan of record in `docs/15-beta-hardening-plan.md`: **(1)** UI rework — real landing page + dashboard
polish modeled on a proven leader, timeboxed reference-pick; **(2)** discovery-agent live run (folds in the
pending 10.1/10.2 smoke) + coverage ledger + low-signal pruning, producing the per-run cost that gates
enabling the ready-but-OFF weekly schedule (D-071); **(3)** bug shakeout from real usage (regression-test
first, D-021) + an optional nightly observability/alert (Hayden's call); **(4)** scaling plan across Neon /
GCP / Resend / Google OAuth **+ Anthropic LLM spend as a fifth pillar** — read the real `pipeline_runs` token
numbers (D-069) and decide the parked Batch API "Block 2"; **(5)** more fetchers, Phenom next (D-052, the
airline portals). **Three scoping choices run through Hayden:** LLM cost **folded into the scaling day**
(not its own day, not deferred); email E2E + `/security-review` **confirmed done** → docs reconciled rather
than re-scoped; deliverable = the ordered plan **+ the doc reconciliation**. **Only hard dependency:** Day 2 →
Day 4 (discovery cost feeds the scaling numbers). **Parked (tracked, not this week):** discovery auto-approval
+ precision eval, non-employer `sources`, actually enabling the weekly schedule, moving vertical config out of
the image (`docs/11` §5). **Status:** accepted; docs written on `docs/beta-hardening-scope`; the per-day work
is the week ahead. References D-067, D-068, D-069, D-071, D-052, D-057, D-021, D-031.

### D-073 · Phase 10.x · Discovery loop cost-hardening (Sonnet 5, $ kill-switch, cumulative caps, caching, checkpoint) · accepted · 2026-07-09
A real `vja-discover` run burned **$7 and produced nothing** — the loop was fundamentally unsafe. Reading the
code found three defects: (1) **no prompt caching** on an agentic loop that re-sends a growing, web-page-stuffed
transcript on every `pause_turn` resume — Opus input price paid uncached on a super-linearly growing prefix;
(2) the **`max_uses` "cap" resets per request**, so the pause_turn resume loop granted a fresh 15-search budget
each turn (observed: 39 searches under a nominal "15") — there was **no real run bound and no dollar ceiling
anywhere**; (3) **all-or-nothing persistence** at the very end, so a killed/failed Stage-1 discarded everything
the money bought. **Decisions run through Hayden (options + recommendation each):** model **Claude Sonnet 5**
(`claude-sonnet-5`, confirmed live via Models API after a stale-catalog miss — standard $3/$15, intro $2/$10 per
MTok through 2026-08-31); hard per-run ceiling **`VJA_DISCOVER_MAX_USD` = $2** (checked after each turn — can
overshoot ~one turn, which caching shrinks); **cumulative** tool budget **8 searches / 8 fetches** (counted from
`server_tool_use` blocks across resumes, the real fix for the reset bug — `max_uses` stays constant per request
so the cached prefix isn't invalidated); checkpoint = **raw report → `data/discovery_reports/` + per-candidate
DB persist**. Non-negotiable fixes: **prompt caching** (`cache_control` ephemeral top-level → growing prefix
re-reads at ~0.1×; SDK-verified param) and **`web_fetch max_content_tokens=5000`**. **Cost rates are
model-aware** (`_model_rates`, longest-prefix; standard list price — conservative so the guard trips early and
survives the Aug-31 intro expiry) replacing the hardcoded Opus constants, so the meter + kill-switch are honest
under any `VJA_DISCOVER_MODEL`. **Shape:** rewrote `discover_candidates`' loop (cache_control, cumulative
`_count_tool_uses` counter, dollar-cost break, `_dump_report`); `_MAX_CONTINUATIONS` env-tunable (12→8 default).
**Net:** a full run now lands well under $1 and **cannot** run away or lose its findings. **Status:** code +
6 tests (dollar ceiling / cumulative tool cap / cache_control+fetch-cap wiring / model rates / tool-use count /
report checkpoint; 409 total) + docs, on `docs/beta-hardening-scope`. Live `vja-discover` walkthrough is
Hayden-run. Supersedes D-070's "bounded by `web_search max_uses` + `_MAX_CONTINUATIONS`" claim (that bound was
theatrical) and D-070's Opus-4.8 model + hardcoded-Opus-rate meter. References D-070, D-069, D-047, D-017.

### D-074 · Phase 10.x · Discovery provider → GPT-5.6 Terra + budgeted ATS-resolution protocol · accepted · 2026-07-10
The first Claude live batch sourced five real companies but resolved zero fetchable ATS boards; broad sourcing
consumed the useful research window and ATS inspection became the unfinished tail. **Decisions run through
Hayden:** migrate only `vja-discover` to OpenAI Responses with **GPT-5.6 Terra** (extraction/matching stay
Anthropic); preserve the two-stage raw-report → structured-candidates protocol and deterministic human-gated
persistence; split sourcing into **three sequential waves** (capital ecosystem, industry ecosystem, market
adjacency), each capped at **5 hosted web actions**; retain at most **5 candidates**, then give each unresolved
candidate a separate **4-action**, low-reasoning, 2k-output, 120s ATS resolver. Resolution requires a canonical
provider URL plus slug/endpoint; “supported” is derived from `SUPPORTED_ATS_TYPES`, never trusted from the model,
and only the existing registry fetch returning ≥1 posting stamps the supported ATS. Confirmed unsupported ATSs
(e.g. BambooHR), blocked pages, no-jobs results, provider failures, and budget exhaustion stay inert as
`unknown`/`layer2`, with typed outcome + evidence in existing `notes` (**no migration**). `--limit` now caps paid
resolution + persistence, not just persistence. Transient provider failures retry twice, checkpoint, and continue
independent work. One rolling Markdown checkpoint updates after every wave/resolver; streamed web events preserve
live progress. The **$4 inclusive ceiling** counts exact permitted-family token/cache rates plus $0.01 billable
search actions; after crossing it no new wave/resolver starts, but one bounded tool-free structuring call preserves
paid work. `VJA_DISCOVER_MODEL` accepts only priced `gpt-5.6-sol|terra|luna`; default Terra. No Anthropic fallback,
auto-approval, schedule enablement, schema change, or BambooHR fetcher. **Status:** built on
`feat/gpt-terra-discovery`; live Terra dry-run remains Hayden-run. Supersedes D-070/D-073 only where they specify
the discovery provider, Claude tool-loop mechanics, tool budgets, model rates, and checkpoint shape; their safety,
validate-by-fetch, inert-proposal, and human-review rules remain. References D-070, D-071, D-073, D-017, D-069.

### D-075 · Phase 10.x · Discovery Responses transport → complete calls, not high-level streaming · accepted · 2026-07-10
The first live Terra aviation run completed wave 1, then OpenAI Python SDK 2.45.0 crashed inside its own
`ResponseStreamState.handle_event`: an output-text event referenced an `output_index` absent from the SDK's
accumulated snapshot, raising a raw `IndexError` before `vja.discover` received the event. The HTTP request had
returned 200; application logging neither caused nor received the failing event. **Decision run through Hayden:**
bypass the fragile high-level stream accumulator for discovery's hosted-web calls. Unstructured research waves use
the complete `responses.create` path; structured ATS resolvers use complete `responses.parse`. This preserves the
same prompts, tool/output caps, timeouts, SDK retries, structured validation, exact completed-response metering,
and rolling checkpoints. The tradeoff is deliberate: retain wave/resolver start/finish + cost logs, but drop
per-search progress events. Catching `IndexError` was rejected because the partially consumed request has no final
usage object and would under-meter spend; a custom SSE accumulator was rejected as fragile SDK-adjacent code.
**Status:** built with a regression test on `fix/discovery-stream-index-error`; no schema or invariant change.
Supersedes D-074 only where it requires streamed web progress. References D-074, D-073, D-021.

### D-076 · Beta hardening · Fetcher build order re-ranked by discovery demand; SWA/Thales are Workday-under-Phenom · accepted · 2026-07-10
The recorded order said **Phenom next** (D-052, docs/15 Day 5). Two evidence sources re-rank it. (1) **Discovery
demand:** per-candidate resolver JSON across the nine `data/discovery_reports/` files makes **Paylocity the #1
unsupported provider** (4 real proposals — Veryon, Trax + 2 grid), then JazzHR (2) and BambooHR (2, incl.
GridBeyond); 8 further candidates resolved to already-supported ATSs and need no work (they auto-activate at
`vja-review approve`). (2) **Live probes:** Southwest + Thales — 2 of Phenom's 3 expected wins — are **Workday
underneath their Phenom skins** (`swa:wd1:external` verified via the existing `cxs` fetcher, 57 jobs;
`thales.wd3`/`Careers`), i.e. config-only onboards; **United is the only real Phenom need** (Taleo underneath, no
clean API there). Feasibility probed live this session: Phenom `/widgets` refineSearch paginates on `totalHits`
(United 155 jobs) with a `jobDetail` lazy-detail call; Paylocity's listing page embeds a complete
`window.pageData` JSON (single response, `JobId` key, empty list-descriptions → lazy detail; the
`/recruiting/v2/api/feed/jobs/{uuid}` endpoint 200s but returns 0 jobs — not the data path); BambooHR
`/careers/list` is trivial single-response JSON. **Decisions run through Hayden:** build order = **Workday config
onboards (SWA/Thales) → Paylocity → Phenom (United) → BambooHR → JazzHR probe/singletons → Layer-2 tail**; the
demand ledger lives in `docs/07` (the Day-2 "coverage ledger" first edition — refresh as discovery runs
accumulate) with docs/15 Day 5 rewritten to match, no new numbered doc; Getro / YC Work-at-a-Startup portfolio
boards are **not** fetcher targets (aggregators — the employer's own ATS is canonical; revisit as non-employer
`sources`, Phase 10). Cheap hardening rides along with the builds: extend `discover._PROVIDER_HOST_MARKERS`
(paylocity/kula/gusto/rippling/trinet_hire/trakstar/pinpoint/phenom) so future runs type these providers
deterministically instead of burning resolver actions. **Status:** docs-only this session (plan of record);
implementation is the next sessions' blocks. Supersedes D-052's "Phenom next" ordering (its
probe-platforms-before-LLM-read rule stands). References D-052, D-070, D-074, D-017, D-072.

### D-077 · Beta hardening · Proposal-correction + new-fetcher activation protocol — `vja-review` tooling, never raw SQL · accepted · 2026-07-11
Live discovery runs left two operator gaps with no legitimate write path. (1) **Misresolved proposals:** real
companies on supported ATSs (e.g. Greenhouse) landed `unknown`/`layer2`; the only documented fix was "seed CSV
or SQL" (docs/14) — i.e. raw SQL against prod Neon. (2) **New-fetcher activation:** when a fetcher ships (next:
Paylocity, D-076), the proposals waiting on it can't be found by `ats_type` — D-074 deliberately never stamps an
unsupported provider on the row, so the evidence (`"provider": "paylocity"`, slug, endpoint) sits in **notes** —
and `vja-review list` can't filter on that. A third defect surfaced reading the code: **`approve` refuses
non-`proposed` rows** (`src/vja/review.py`), contradicting its own docstring and D-071's "fixing a parked row's
`ats_type` and re-approving promotes it" — parked (`approved`) rows are unpromotable. **Decisions run through
Hayden:** corrections go through `vja-review` — never raw SQL on prod, and not CSV-graduation (it bypasses the
review gate and muddies `source=agent_discovered` provenance; CSV + `vja-import-employers` stays the path for
*curated seed* rows only, e.g. the SWA/Thales Workday flip). New **`set-ats <id> --ats-type --slug/--endpoint`**
subcommand: **validates by actually fetching** (registry fetcher must return ≥1 posting — the same D-070 gate
the agent is held to) before stamping `ats_type`/`ats_slug`/`endpoint`/`verification=verified` + an audit note;
it never touches `status` — `approve` stays the only promotion gate. **`list --provider <x>`** matches notes
evidence + `ats_type` to find a new fetcher's waiting rows. The sweep is a **composed runbook** (docs/14), not a
batch `activate` command — volumes are 2–4 rows per fetcher and each slug/endpoint deserves human eyes. The
**parked-re-approve bugfix rides along** (failing regression test first, D-021): `approve` must promote
`approved` rows whose ATS has become fetchable. Misresolved rows stay inert until the tooling ships — **no
interim SQL**. **Status:** protocol decided, docs-only this session; build rides with the Paylocity fetcher
block (D-076 step 9). References D-071, D-074, D-070, D-076, D-021.

### D-078 · Beta hardening · Coverage-audit findings + demand-ranked fetcher plan (Pinpoint first) · accepted · 2026-07-12
A read-only audit of prod Neon (135 employers; 63 fetchable, 62 fetched by run #18) triaged all 72 unfetched
rows with live probes (registry-fetcher validation — the `set-ats` gate — plus careers-page signature
detection). **Findings:** (1) six discovery rows validate on *already-supported* ATSs today — ASI (ashby,
26 postings, approve-only), GridBeyond (bamboohr `gridbeyond`, 2), CivilGrid (ashby `civilgrid`, 6), Emerald AI
(ashby `emerald-ai`, 7), AiDASH (greenhouse `aidashinc`, 12), Aloft (greenhouse `versaterm`, 34 — but the board
is parent Versaterm public-safety software; Hayden's call) — activated via the D-077 runbook, no code. (2)
**Honeywell's canonical Oracle host was found** (`ibqbjb.fa.ocs.oraclecloud.com`, siteNumber `CX_1`, via the
careers page's `og:image`; 1,455 postings validated; constructed apply URL resolves 200) → curated seed-CSV
onboard **lands this session** (aviation fetchable 14→15, total 47→48). (3) **Con Edison's host was found too**
(`ejcu.fa.us6.oraclecloud.com`, `CX_1033`) but fails paginate-or-fail deterministically at **61 of 62** — a
bug-shakeout candidate; do not retire. (4) **Jeppesen (Boeing) is duplicate coverage** — the Boeing Workday
board it points at is *already fetched* (seed row `Boeing`, `boeing:wd1:EXTERNAL_CAREERS`); recommend CSV
`status=retired` (the Navitaire/Amadeus case), decision Hayden's. (5) Comply365/Vistair validates on BambooHR
(`vistairhr`, 11 postings) but was never persisted to the DB — candidate curated seed add. (6) ~30 rows are
genuine dead ends (email-only application, bot-blocked, EU-only, careers-404) — retire slate stays a
Hayden-executed runbook (chat, per his call: no repo audit doc). **Decision — next fetchers, re-ranked by this
audit's demand evidence** (supersedes D-076's tail ordering; Paylocity/Phenom/BambooHR are done): **1. Pinpoint**
(clean public JSON `GET {tenant}/postings.json`, single-response, BambooHR-parity build; +2 immediately: Aireon
`aireon.pinpointhq.com` + Aurora Energy Research `careers.auroraer.com` — a Pinpoint custom domain, both
live-verified) → **2. Radancy variants** (extend the existing fetcher: L3Harris `/en/search-jobs/results`
returns clean JSON `{filters,results,hasJobs}`; NRG's table rows carry no job link + "Results 1 – 10" aria
format; American Airlines + Bombardier render no `searchresults` table; National Grid 403s — up to +5, AA is a
flagship) → **3. JazzHR** (server-rendered HTML boards at `{slug}.applytojob.com` + custom domains; Utilidata +
Near Earth Autonomy, +2) → **4. Jobvite** (server-rendered `jobs.jobvite.com/{slug}/search`; Uplight `uplight` +
Enverus `drillinginfo`, +2) → **5. Taleo** (one `textron.taleo.net` tenant covers Bell + Textron Aviation, +2)
→ singleton tail unchanged (Eightfold/UKG/Avature/TriNet/Rippling/Gusto/Kula/Personio opportunistic;
SuccessFactors stays deferred). Projected: 63 → ~72 with no code (runbook + Honeywell), → ~83 with builds 1–4.
**Status:** accepted; Honeywell CSV + docs land this session, builds are next sessions' blocks. References
D-076, D-077, D-051, D-052, D-070, D-017.

### D-079 · Phase 8: Pinpoint fetcher + explicit-endpoint override for provider custom domains · accepted · 2026-07-12
D-078 ranked Pinpoint first and live probes confirmed one uniform unauthenticated contract on both the canonical
Aireon tenant and Aurora Energy Research's custom domain: `GET {board}/postings.json` returns one rich
`{"data": [...]}` response (2 and 87 jobs respectively at verification). **Decisions run through Hayden:** one
generic rich-list fetcher; canonical tenants derive `https://{slug}.pinpointhq.com/postings.json`, while an
an explicit Pinpoint endpoint overrides its derived template so provider-backed custom domains stay config-only
without changing existing derived-provider endpoint behavior.
The clean `data` array is authoritative (valid empty = zero open; malformed response/entry or duplicate id fails
the whole fetch). `external_id` is the top-level posting `id`, not nested `job.id`; title is trimmed, apply URL is
the supplied absolute `url`, location is `location.name`, and `updated_at=None` because the source exposes no
posted/updated timestamp. The list already contains the complete split job content, so there is no lazy detail
resolver; description/responsibilities/qualifications/benefits/compensation are joined only for stable content
hashing while the untouched object remains `raw`. Aurora onboards through curated seed config; Aireon stays on
the D-077 discovery-proposal activation path after deployment. `pinpoint` fits the existing application-validated
`VARCHAR(15)`, so no migration. **Status:** built on the Pinpoint-only branch. References D-078, D-077, D-017,
D-016, D-021.

### D-080 · Beta hardening · UI rework scope: Linear reference, design language v2, 4-PR block · accepted · 2026-07-12
The docs/15 Day-1 "UI rework" item is scoped (planning session; every decision below is Hayden's, via
questionnaire). **Reference = Linear** — the landing page and app UX copy a proven leader rather than invent
(the D-072 "timeboxed reference-pick" resolved). **Design language v2, everything on the table:** the v1
"terminal dev-tool, dark" DESIGN.md is revised toward **softer, more premium dark** — the orange `#f6821f`
accent, the Space Grotesk/JetBrains Mono pairing, and the terminal motifs (`$` prompt, blinking ▮ cursor,
`//comment` strings) are all up for replacement; Claude drafts the revision, and the accent + font picks get
Hayden's sign-off from screenshot comparisons on the real dashboard before landing. **Scope expands Day 1 to a
4-PR block, strict merge order** (plan of record: `docs/16-ui-rework-plan.md`): **PR 0** design-language
foundation (DESIGN.md v2 + `theme.css` tokens + app shell) → **PR 1** full Linear-style marketing landing
(hero + how-it-works + verticals + footer; the product visual is a CSS-built mock on real tokens, no binary
asset) → **PR 2** login/onboarding polish (auth card + descriptive vertical cards + drag-drop upload; also
fixes Login's stale "browse without signing in" copy, false since D-067 flipped `VJA_AUTH_REQUIRED` on) →
**PR 3** dashboard rework (row-level match info — verdict/score + rationale snippet visible without a click —
Linear-style side-panel detail replacing inline expansion, client-side sortable columns + text filter).
**Everything is frontend-only:** `GET /api/postings` already returns the full filtered set server-sorted with
no pagination (`db/postings.py`), so sorting/filtering is client-side and no API contract moves. Standing
rules hold: Rolefeed brand, D-065 route guards, D-064 one-vertical (no cross-user picker), frontend gate +
screenshots per PR, branch-only. **Explicitly out:** mobile pass (deferred, strong later candidate), keyboard
navigation (offered, not selected), backend-assisted sorting. **Why:** the beta surface must sell before
broader invites, and copying a leader converts taste questions into execution questions; the separate
foundation PR keeps the token swap reviewable and lets PRs 1–3 land on merged tokens. **Amends D-072's
"one day" sizing for this item.** References D-072, D-042, D-064, D-065, D-067, D-068, D-021.

### D-081 · UI rework PR 0 · Design language v2 tokens: Indigo · Inter (candidate A) · accepted · 2026-07-12
The D-080 sign-off ran as designed: three candidate token sets were rendered **on the live dashboard with real
data** (runtime style injection over the built SPA, Playwright + system Chrome against the local DB) and
presented as a screenshot comparison next to the v1 baseline — A "Indigo · Inter" (the full Linear move),
B "Amber · Geist" (brand-continuity accent), C "Violet · Space Grotesk" (keep type, move accent). **Hayden
picked A.** The v2 language ("premium dark product", DESIGN.md rewritten): blue-tinted near-black ground
(`#08090c`/`#0f1014`/`#16171d`), muted indigo accent `#6e79d6` (tint `#191b2e`/`#a5adf0`), softened success
`#4cc38a`, borders `#24252d`; **Inter** carries all UI text (body letter-spacing −0.1px), **JetBrains Mono is
reserved for true data** (scores, dates, tags, company cells, paths) — never buttons/nav/labels/prose; soft
`--shadow-raised` on raised containers (borders stay primary); radius 10px + 6px chips. **Terminal motifs
retired** in code, not just prose: the `$` prompt + blinking ▮ wordmark → a 9px indigo mark + "Rolefeed" in
Inter 600; `//comment` notice prefixes and the `~/vertical` path chrome dropped (vertical renders as a tint
chip); the footer's decorative `↵ open` hint (rows only respond to click) → honest "Click a row to expand".
Google-Fonts import swaps Space Grotesk for Inter. Frontend-only; all 45 vitest + eslint + tsc green; v1's
tokens survive nowhere (theme.css fully rewritten). **Why record the pick:** D-080 left accent + font open
pending screenshots; this closes it so PRs 1–3 build on a decided, merged token set. References D-080, D-042.

### D-082 · Beta hardening · Onboarding overhaul: upload-flow fixes, backfill-status signal, welcome-slides tutorial · accepted · 2026-07-13
The first real private-beta user hit onboarding friction end-to-end (outdated résumé → confusing reupload,
"stuck on the upload page", ambiguous dashboard toggles), and exploration confirmed a concrete root cause for
every complaint: the upload submit's only feedback is a button label and the post-202 `/api/me` refresh flips
the global `loading` flag (the whole route blanks to "loading…" mid-submit) with no timeout and two failure
races (a spurious error after a successful upload; a profile-visibility race that bounces the user back to
`/onboarding`); an edited résumé's new `resume_version` orphans every prior match so the matched view goes
near-empty until the nightly; nothing tells the client whether the backfill is running; `/upload` has no back
navigation; the toggles have zero explanation; and no tutorial affordance exists. **Decisions (all Hayden's,
via questionnaire): (a) build a real backend backfill-status signal** — `run_backfill` stamps
`backfill_started_at`/`backfill_completed_at` on the profile (new columns, additive migration; a new résumé
version is a new profile row so status is naturally per-version), `/api/me` exposes a derived
`backfill_status: running|done|null`, and the dashboard's poll keys off it (survives refresh, works on
reupload; a stale "running" older than ~10 min reads as done). **This supersedes D-057's "no backend
push/status endpoint" clause**; the bounded client-side poll survives as the consumer. **(b) Reupload
semantics affirmed** = instant 5-day/100 backfill + the already-uncapped nightly re-match, surfaced honestly
in the UI ("recent roles re-match within minutes; full refreshed results after tonight's run") — an immediate
full re-match was rejected (~$3/event at ~314 in-scope open postings vs the $5 daily ceiling, user-triggered
burst surface). Old-version matches stay DB-only audit rows; the dashboard join on the active
`resume_version` means old and new verdicts never mix. **(c) First-run tutorial = welcome slides** (multi-step
dialog on the `PostingPanel` pattern; 3–4 slides: nightly diff + digest · matched vs cleaned · recency windows
+ detail panel · résumé updates), seen-flag in `localStorage`, re-openable via a "?" nav button — coach-marks
tour rejected as heavier build for beta. **Shape: 3 PRs** (plan of record `docs/17-onboarding-plan.md`):
PR 1 upload/onboarding bug-fix tier (frontend + one backend regression test pinning the previously unpinned
API-level reupload path; includes the commit-point rule — after a 202 the upload can never present as failed —
plus upload timeout, silent bounded `/api/me` retry, `/upload` back nav, keep-data-while-polling) → PR 2 the
status signal (migration + stamps + `/api/me` + banner; INVARIANTS' D-057 poll line rewritten when it lands) →
PR 3 tutorial + toggle tooltips/labels (copy = Hayden sign-off at execution). Groups with the docs/15 Day-3
bug shakeout as its fresh-account leg. References D-057, D-064, D-065, D-021, D-068. **Amends D-057.**

### D-083 · Onboarding incident · Schema readiness + honest auth-probe failures · accepted · 2026-07-13
PR #79 deployed the D-082 backfill-status code while production Neon was still at `b2f4c1a9e07d`.
The migration had been run, but a bare `uv run alembic upgrade head` does **not** load `.env` and
therefore upgraded the default local SQLite DB, not Neon. The new `/api/me` query raised
`UndefinedColumn(backfill_started_at)` in Cloud Run. A second bug converted every non-401
`/api/me` failure into `me=null`, so the SPA rendered the logged-out Landing page after a successful
OAuth callback and hid the real 500. Production recovered by explicitly exporting the Secret
Manager `VJA_DATABASE_URL` and applying `a06b99424c4c` to Neon.

**Decision:** manual migrations stay manual and pre-merge (D-068), but the production image now
sets `VJA_ALEMBIC_INI=/app/alembic.ini` and the API lifespan compares the DB's Alembic revision with
the migration head packaged in that image. A known older revision fails startup, so Cloud Run never
makes the incompatible revision ready and the prior revision keeps serving. A DB revision unknown to
an older image is allowed with a warning: this is the normal additive-migration rollback case, and a
cold-starting old revision must remain viable. Local/test processes stay opt-in by leaving the env
unset. This is a last-line compatibility guard, **not** an automatic migration and not permission to
merge code before migrating Neon.

**Frontend follow-through:** 401 remains the only logged-out signal; a thrown `/api/me` probe shows a
retryable account-load error rather than Landing, and an authenticated visit to `/login` routes to
that user's onboarding/dashboard destination. The adjacent upload-response contract is corrected:
`resume_version` is a string, matching FastAPI. **Status:** built on
`fix/onboarding-auth-failure`. References D-082, D-068, D-067, D-065, D-021.

### D-084 · Discovery operations · Live-run gate complete; run manually/on demand, never on a recurring schedule · accepted · 2026-07-13
D-071 shipped the discovery scheduler as ready-but-OFF until live cost and yield were known. That gate is now
complete: multiple full GPT-5.6 Terra runs exercised all three research waves plus per-candidate ATS resolution
on both verticals, with complete-run estimates of approximately **$0.77–$0.99** and rolling evidence under
`data/discovery_reports/`. The coverage ledger exists (`docs/07`), the production coverage audit produced the
low-signal retire slate, and D-077's `vja-review` correction/approval path makes the results operable. **Decision
(Hayden): discovery remains manual/on demand.** Run `vja-discover` only when the employer universe needs a
refresh; do not create or enable a weekly Cloud Scheduler/launchd trigger. The disabled templates/runbook remain
available machinery, not unfinished work. Proposal activation, retirement, and new-fetcher sweeps continue as
ordinary company-database curation behind the human gate. **Status:** accepted; closes docs/15 Day 2 and
supersedes D-071 only where it frames measured cost as a gate to a future schedule-enable decision. D-071's
human approval, inert-proposal, and swappable-trigger rules remain. References D-071, D-074, D-077, D-031.

### D-085 · Beta hardening · Closeout sequence + post-onboarding product focus · accepted · 2026-07-13
After UI PRs #74–77, onboarding PRs #78–79, and incident hotfix #80 merged, Hayden re-ran the remaining
beta-hardening scope. The old plan also said "six items" while enumerating only five and still described merged
work as pending. **Accepted sequence:** (1) finish onboarding PR 3 first: four welcome slides (nightly Rolefeed ·
Matched for you · every in-scope role · details/résumé updates), controls **Skip / Back / Next / Start exploring**,
view labels **Matched for you / All in-scope**, recency labels **New today / 1 week / 2 weeks / All open**, move
the table-use/read-only/nightly hint above the results, and display internal `aviation_software` as **Aviation
Technology** without renaming the config/API/DB slug. (2) A separate landing PR gives each section one job —
three cards = user benefits, How it works = pipeline mechanics, Why I built this = Hayden's recruiting problem
and thesis — and broadens outward *software roles* language to *technology roles* so analyst/data work fits.
(3) A separate abuse-control PR makes identical-content reuploads a success with no new backfill and limits a
changed résumé to **one reupload per user per rolling 24 hours**, server-enforced with 429 + `Retry-After`; the
first upload remains allowed. (4) D-069 Block 2 now runs **correctness before discount**: production logs on
July 8–10 showed 343–654 new and 384–592 closed postings per night with the same 44 fetched employers, while
extraction dominated roughly $0.63–$1.65 nightly spend and matching usually hit 84–93% prompt cache. Diagnose
the posting identity/diff churn first, re-measure steady state, then batch **extraction first** if it remains
material; do not make a correctness bug merely cheaper. (5) The beta exit also includes resolving the live
robotics-promise/config mismatch, minimum Cloud Job monitoring, the five-pillar scaling assessment, and the
already-validated no-code employer activations. Scheduled discovery and an endless fetcher queue are not beta
exit gates. **After onboarding, the main loops are UI/UX iteration, building the employer databases, and beta-user
feedback.** Status: planning/docs accepted; only D-084's scheduling rule is live now. The PR-3 UI, landing,
reupload guard, churn fix/Batch work, monitoring, and scaling assessment become live only when their own tested
PRs land. References D-069, D-072, D-078, D-080, D-082, D-083, D-084, D-021.

**Implementation update · 2026-07-16:** PR-3 is live via #82, landing copy via #86, the reupload guard
via #87, and the D-088 snapshot-integrity guard via #88. Neon was explicitly verified as
`PostgresqlImpl` and advanced to `c4e8a7d9132f (head)` before #87 merged. The July 16 nightly started
before #88 merged, so July 17 and 18 are its two production observation nights. Monitoring and the
scaling assessment remain planned.

### D-086 · Beta hardening · Nightly task timeout/retry guard prevents duplicate digest delivery · accepted · 2026-07-14
The first nightly after another beta signup exposed an attempt-level delivery defect. Cloud Run execution
`vja-nightly-zvw6s` ran the sequential pipeline under the existing **7,200-second timeout + one retry**:
attempt 0 completed aviation Layer 2 and sent both aviation digests, then timed out while grid was still
running; Cloud Run restarted the entire command as attempt 1, which sent aviation again before completing
grid. Production evidence ruled out duplicate profiles: every affected recipient had one active profile,
and the digest audit rows matched the two task attempts. The new grid user received one correct digest only
on attempt 1 because attempt 0 never reached grid's send phase.

**Immediate decision:** the Cloud Run nightly Job uses a **21,600-second (6h) task timeout and zero automatic
task retries**. `deploy/gcp/ship.sh` reasserts both values on every deploy, the cutover/create runbook carries
the same flags, and an offline regression test pins the deploy contract. The current beta run took under
three hours even with the retry, so six hours restores headroom. Because the pipeline isolates most provider,
vertical, and send failures internally, a remaining process-level failure is safer as a visible failed Job
and an operator-reviewed manual rerun than as a blind whole-command retry that can resend completed verticals.

**Follow-up, not in this quick guard:** durable delivery idempotency keyed to the Cloud Run execution/attempt
boundary, after which automatic retries can be reconsidered. This does not close D-085's minimum platform-level
Job monitoring item; a killed process cannot send its own in-process alert. References D-031, D-068, D-085,
D-021.

### D-087 · Product roadmap · Post-beta feature slate: intraday freshness + alerts, salary, gaps report, lifespan intel · accepted · 2026-07-14
Hayden set the post-public-beta product frame — **new** = jobs grouped by a niche vertical, **better** = AI
matching, **proven** = a job-finding tool — and benchmarked jobright.ai: minute-level freshness ("posted 10
minutes ago" on a wanted role feels like striking gold) and salary display are its standout features, while
most of its remaining surface (résumé editing, networking matches, autofill apply) reads as clutter.
**Selection rule adopted: adapt 1–2 proven features, add something genuinely novel, resist clutter.**

**Accepted slate (plan of record: `docs/18-post-beta-features.md`):** (F1) **intraday freshness + instant
alerts** — poll fetch→diff→extract→match every ~1–2h via a new scheduled Job, alert relevant-verdict matches
immediately with an alerted-at idempotency marker, digest stays the nightly roll-up; the bounded ~66-employer
universe makes intraday polling cheap and polite where horizontal boards can't follow, and total LLM spend is
roughly unchanged because only diff items are extracted/matched. (F2) **salary** — Phase A surfaces the
already-extracted `comp_min/comp_max/comp_raw` (stored since Phase 5, never displayed; fill-rate query first);
Phase B enriches comp-less postings from public DOL H1B/LCA wage-disclosure files filtered to our employer
universe, honestly labeled as visa-disclosure-based estimates. **Glassdoor/Indeed is a closed path** — no open
API exists and scraping violates their ToS plus our politeness-is-policy invariant. (F3) **recurring-gaps
report** (novel) — aggregate the profile's stored `matches.gaps` periodically into "the #1 thing between you
and strong_yes," one cheap metered LLM call per user per period, feeding the résumé-update→re-match loop.
(F4) **urgency/lifespan intel** (novel; the D-009 promise) — per-employer median posting lifespan from
`first_seen_at`/`closed_at` → "typically fills in ~N days" + closing-soon flags; read-only, zero LLM.
**Rejected for clutter/honesty:** YOE/new-grad flags (redundant — the platform is early-career by
construction), networking matches, autofill apply (collides with no-auto-apply), applicant counts (no honest
source; freshness is the substitute signal).

**Hard prerequisite:** the D-085 posting-identity/diff churn diagnosis now **blocks F1 and F4** — intraday
polling would amplify churn into alert spam and repeated LLM spend, and churned close/reopen cycles corrupt
lifespan medians. **Sequence (post-beta-exit):** churn diagnosis → F2 Phase A → F4 → F1 → F3, with F2 Phase B
as a parallel data-only track. **Status: planning/docs accepted; nothing is live.** All beta-exit work
(D-085) precedes this slate. D-005's once-daily-fetch rule remains authoritative in `docs/INVARIANTS.md`
until F1's own build ADR supersedes it. References D-085, D-005, D-009, D-086, D-035, D-069, D-053.

### D-088 · LLM-cost Block 2 · Conservative snapshot-integrity guard before any batching · accepted · 2026-07-15
Production cost exports and run logs showed that extraction, not matching input, was the main avoidable
nightly LLM expense, but also exposed abnormal posting churn: stable 44-employer runs on July 8–10 reported
343–654 new and 384–592 closed postings per night. The exports do not prove one root cause. The code audit did
prove a concrete completeness vulnerability: Workday, iCIMS, Oracle, SmartRecruiters, and Radancy read only the
first pagination total and accepted any final count at or above it; then `sync_employer` silently collapsed
duplicate `external_id` rows into a dict before diffing. A drifting/duplicated snapshot could therefore look
complete while omitting real postings, producing false closures and unnecessary re-extraction when they return.

**Decision (Hayden): correctness-first, conservative scope.** Every affected paginated fetcher reads the total
on every page, fails if it changes, and requires an exact final mapped count. Independently, the shared pipeline
rejects duplicate ATS `external_id` values before opening the employer transaction, so the whole employer
snapshot fails with zero posting mutations. Identity remains exact ATS ID (D-016): no fuzzy title/location
dedupe, schema change, repair job, full-board double-fetch/bookend, or anomaly-confirmation heuristic is added.
Changed employers log fetched/new/reopened/updated/closed/unchanged counts and failures log employer/provider +
reason, providing attribution without a new persistence ledger.

Live verification found the concrete Radancy instance behind that risk: its board ignores the previously
documented `CurrentPage`/`RecordsPerPage` parameters, so the old fetcher repeated page 1 until its accumulated
row count crossed the total. The board's rendered pagination links use `startrow`; offsets 0/25/50/275 returned
disjoint pages and an exact 290-row snapshot. D-088 therefore corrects Radancy to advance by mapped-row offset
and supersedes D-052's `CurrentPage` implementation detail while leaving D-052's platform/mapping decision intact.

**Cost decision:** do not implement Anthropic Message Batches now. Rolefeed is time-sensitive and the Batch API's
up-to-24-hour completion window conflicts with timely delivery. Keep synchronous extraction/matching, observe
two production nights after this fix, and re-measure steady-state spend/churn. If extraction remains material,
reconsider extraction-first batching; matching is already highly prompt-cache-efficient. This fix closes a
demonstrated vulnerability, not the entire churn diagnosis; only the observation window decides whether a
bookend/anomaly-confirmation follow-up is justified. References D-016, D-021, D-035, D-069, D-085, D-087.

### D-089 · Beta hardening · Normalize out-of-range integer match scores without an LLM retry · accepted · 2026-07-16
A read-only production shakeout found **26** match calls on the July 16 nightly rejected solely because Sonnet
returned a score below the required 0–100 range (`-1` in 25 cases, `-5` once); the same signature occurred 56
times across seven execution dates since July 7. The otherwise structured result was discarded, no match row
was saved, the pair remained eligible for another paid nightly attempt, and the call's usage never reached the
meter because `messages.parse` raised during its response post-parser. The prompt and Pydantic field already
state 0–100. Inspection of the locked Anthropic SDK identified the seam: its schema transform preserves the
integer type but moves unsupported JSON-Schema `minimum`/`maximum` constraints into descriptive text, so the
API can return an integer that local Pydantic then rejects.

**Decision (Hayden): deterministic boundary repair, no second model call.** Before the strict field constraints
run, a real integer below 0 clamps to 0 and one above 100 clamps to 100; every repair emits a warning with the
original and normalized value. The final `ge=0`/`le=100` contract remains in force. Wrong types, malformed JSON,
missing fields, and every non-boundary validation failure still fail and isolate at the posting boundary. No
prompt, model, schema, migration, frontend, or retry policy changes. This preserves the paid fits/gaps/verdict/
rationale, records the call's normal usage, saves the match once, and prevents the same pair from being billed
again merely because its score missed the boundary. Regression coverage pins both boundaries, logging, strict
wrong-type failure, persistence, and next-run idempotency. **Status:** built on
`fix/match-score-boundary`; Hayden owns commit/PR. References D-007, D-021, D-035, D-069, D-085.

### D-090 · LLM optimization · Embedded LiteLLM boundary first; model cutovers require separate eval gates · accepted · 2026-07-16
Claude Sonnet and Haiku currently produce trusted output, but their fixed provider-specific integration and
hardcoded prices make it costly to test whether a cheaper model can preserve quality. Hayden approved a
sequenced pre-beta/Robotics optimization program (plan of record: `docs/19-llm-optimization-plan.md`): observe
the D-088 production fix first; build a provider-neutral boundary at Anthropic parity; expand the synthetic
multi-model eval and repair its missing path-filtered CI job; then decide extraction, matching, and `no`-output
cutovers as separate reviewed blocks.

**Block-1 decision:** embed the LiteLLM Python SDK (no proxy/router). `vja.llm` owns transport, structured
parsing, mutually exclusive token/cache normalization, LiteLLM catalog cost, actual upstream model, latency,
and request ID. Extraction and matching depend only on its typed local contract. Call-time routes default to
`VJA_EXTRACT_MODEL=anthropic/claude-haiku-4-5` and
`VJA_MATCH_MODEL=anthropic/claude-sonnet-4-6`; Sonnet keeps `VJA_MATCH_EFFORT=medium`, which LiteLLM maps to
Anthropic adaptive thinking plus output effort. The current prompts, schemas, cache breakpoint, max tokens,
D-089 clamp, isolation, idempotency, and existing DB schema remain unchanged. The actual response model is
persisted and returned catalog costs are aggregated into the existing nightly ledger.

**Original Block-1 rule (superseded by the July 21 amendment below):** unsupported parameters or missing
pricing/usage fail loudly; parameter dropping is disabled, a nonempty paid response may not become `$0`, and
there is no automatic routing, fallback, or new retry policy. No model,
prompt, schema, secret, provider, database, discovery-agent, or `no`-verdict behavior changes in Block 1.
The existing Anthropic eval is a manual parity gate here. D-020/D-021's path-filtered eval policy remains the
target, but the current CI workflow has no eval job; Block 2 must restore it with the expanded harness before a
model cutover. This supersedes D-011's direct-Anthropic-SDK implementation choice and amends D-035/D-036's
fixed model names into eval-gated configured defaults, without changing today's models. References D-005,
D-007, D-020, D-021, D-035, D-036, D-069, D-088, D-089.

**Implementation status:** Block 1 merged as PR #90 and deployed to the Cloud Run service + nightly Job as
image `07ed265` on 2026-07-16. Health returned 200, the anonymous postings guard returned 401, and the Job is
Ready with the existing Anthropic secret, six-hour timeout, zero retries, and no model-route overrides.

**Lean-plan amendment (Hayden, 2026-07-21):** exact cost is tracked in provider dashboards, so catalog
pricing is useful telemetry but not a correctness dependency. Usage/model/latency remain required; a
missing or invalid LiteLLM price warns, returns `cost_usd=None`, and makes the aggregate
`pipeline_runs.llm_cost_usd` null rather than failing a valid response or recording a false `$0`. Stable
LiteLLM 1.93 is required for DeepSeek V4's explicit non-thinking mode. Remaining work is three small,
separately reviewed blocks: provider readiness; a modest extension of the existing extraction eval plus
DeepSeek V4 Flash cutover; and a modest extension of the existing matching eval plus GPT-5.6 Luna cutover.
The first model-changing branch restores D-020/D-021's path-filtered eval CI gate, but no generic benchmark,
pricing overlay, payload compactor, new prefilter, cache redesign, or paid-failure ledger is authorized.
The proposed `no`-output optimization is retired: matching reasons before its verdict, so shortening the
stored payload is not expected to remove the material reasoning-token spend. This paragraph supersedes
D-090's missing-price failure and fourth-follow-on requirements; all other boundary rules remain.

**Extraction decision (Hayden, 2026-07-21): retain Haiku.** The lean extraction eval now covers six
representative postings and four literal anti-hallucination rules (unknown seniority, remote geographic
eligibility, no hourly annualization, and publication-date provenance). On the final tuned prompt, production
Haiku passed 6/6, DeepSeek V4 Flash passed 5/6, and DeepSeek V4 Pro passed 4/6. Both DeepSeek candidates missed
explicit remote-US location; Pro also mislabeled a 3–5-year Engineer II role. They are rejected after the
approved single tuning round, so no DeepSeek adapter, secret, model route, or deployment change is warranted.
The useful universal prompt rules and six-case manual Haiku eval remain; matching/Luna is the next separate
decision. **Extraction amendment (Hayden, 2026-07-22):** real extraction output is nondeterministic evidence,
not a merge gate. The first solid Haiku baseline scored 5/6, so one varied fixture or provider outage must not
block a code PR. This narrowly supersedes D-020/D-035's extraction-gate requirement: run the small metered suite
manually for model/prompt decisions and apply human judgment. Matching's policy remains for its separate Block 4
decision. The proposed automatic extraction workflow and GitHub Actions model-secret dependency are removed.

During candidate testing, a provider SDK traceback retained request details and rendered the then-current local
DeepSeek key. Hayden rotated it immediately. `vja.llm` now replaces every provider-call exception at the boundary
without chaining it, retaining only model route, exception class, and integer HTTP status; a regression formats
the full traceback and proves that keys and prompt text are absent. No key value entered the repository diff,
and DeepSeek never reached production configuration.

### D-091 · Workday incident · Quarantined pagination trace before changing the completeness contract · accepted · 2026-07-17
The first D-088 production run succeeded once in 33m35s, but 14 otherwise-healthy Workday tenants failed on
page two with the same HTTP-200 shape: page one reported a nonzero total and page two reported `total=0`.
GE Vernova's separate missing-title failure remained unchanged. Existing logs preserved the two totals but
discarded the page rows before the exception, so they could not distinguish valid disjoint pagination from an
ignored offset, a premature empty page, or malformed rows. Hayden explicitly chose evidence before a contract
change: do not guess that later zero totals are safe, and do not re-hit a board after the once-daily run.

**Decision:** on the first Workday total mismatch, permanently quarantine that employer snapshot, then finish
one bounded diagnostic pagination walk against page one's total before raising the original `FetchError`.
The trace records page/offset/limit, expected and reported totals, row/cumulative/unique counts, overlap and
malformed-ID counts, a hash of ordered public external IDs, HTTP status/latency/response size/content type,
safe request-ID headers, and a final `would_complete` summary. It never logs raw payloads, job identities,
titles, locations, or descriptions. The fetcher has no DB connection; the invalid snapshot is never returned,
so diffing and posting mutation remain impossible. Stable-total snapshots retain their existing behavior.

The July 18 scheduled run is the live evidence gate; no manual duplicate fetch is added. If zero-total pages
are complete and disjoint, a later decision can safely define page one as authoritative. Repeats, empties,
short/over counts, or malformed rows instead point to the corresponding request/mapping defect. This is
diagnostic instrumentation, not the Workday contract fix. References D-005, D-016, D-021, D-032, D-088.

### D-092 · Workday incident · Two valid later-page total modes; ambiguous 2,000-result boards stay failed closed · accepted · 2026-07-21
PR #92 did not merge until July 20, so the July 21 scheduled execution `vja-nightly-djxjt` was the first run
that actually carried D-091's trace (the planned July 18 gate in D-091/docs was stale). It completed once in
34m39s with zero retries. All 15 fetch failures were Workday boards whose first nonzero total became zero on
page two. Every one then returned disjoint pages that exactly reached page one's target, with equal collected
and unique counts, zero overlap, and zero malformed IDs. Four other multi-page Workday tenants repeated the
original total and also completed exactly. The evidence distinguishes two real cxs tenant contracts rather
than a broken offset: later pages either repeat page one's total or consistently use zero as a sentinel.

**Decision (Hayden): accept both modes without weakening D-088.** Page one remains the authoritative target.
Page two selects `stable` (repeat the target) or `first_page_only` (`total=0`), and every remaining page must
stay in that mode. Any other drift, mixed mode, request/shape/mapping failure, early empty page, short/over
count, duplicate ID, or malformed ID rejects the employer snapshot before mutation. D-091's quarantined
shadow walk is retired: page evidence moves to debug and one compact completeness summary remains at info.

**Cap exception:** 13 of the 15 first-page-only boards ended with a short final page and are accepted by this
contract. Airbus and Thales each reported exactly 2,000 and returned 100 completely full pages. That proves
agreement with the reported target but not source completeness and strongly matches a result cap, so this
specific first-page-only/full-page signature raises an explicit cap `FetchError`. Their existing rows remain
untouched; no broad acceptance, facet-partition strategy, manual refetch, or config/Layer-2 reclassification is
part of this branch. References D-005, D-016, D-021, D-032, D-046, D-088, D-091.

### D-093 · LLM optimization · Luna low replaces Sonnet for matching; live evals stay manual · accepted · 2026-07-22
The approved eight-case grid/aviation/robotics comparison measured Sonnet 4.6 medium at **7/8**, GPT-5.6
Luna low at **8/8**, and Luna medium at **8/8**. Sonnet promoted the intentionally ambiguous mid-level/domain-fit
case to `yes/72` twice; both Luna efforts kept it at `maybe/48`. Luna low met the same 8/8 trust bar as medium
with lower latency and token use, and its catalog estimate was about 63% below Sonnet's over the fixture set.
Hayden selected `openai/gpt-5.6-luna` at `low` effort.

One human-reviewed prompt-calibration round makes relevant internships/coursework/projects real evidence at
new-grad and early-career levels without weakening mid/senior or hard-eligibility guards. Domestic location is
logistics, not match quality: for US roles, an unstated willingness to relocate or work onsite may be mentioned
but never lowers verdict/score; explicit country/work-authorization incompatibility still counts, and Stage B's
confirmed-non-US filter remains unchanged. The tuned Luna-low run passed 8/8 and improved two conservative
positives; one malformed `fits` fragment did not repeat on its allowed rerun, so no one-off cleanup heuristic or
retry policy was added.

Real matching output is nondeterministic evidence, not an automatic merge gate. Future model/prompt decisions
must run the small metered suite locally, preserve the complete outputs, and receive Hayden's explicit signoff.
Deterministic schema/routing/persistence tests remain hard CI gates. Do not add a provider key, paid eval job, or
benchmark subsystem to GitHub Actions without a concrete new use case. This supersedes D-020/D-021 and D-090's
unimplemented path-filtered live-eval requirement for matching; extraction already follows the same manual rule.
Provider-call exceptions still cross `vja.llm` through the D-090 secret-safe, unchained boundary.

Deployment mounts the existing `OPENAI_API_KEY` Secret Manager entry on both Cloud Run targets and explicitly
preserves `VJA_MATCH_MODEL=openai/gpt-5.6-luna` plus `VJA_MATCH_EFFORT=low`; Sonnet medium remains the env-only
rollback. Future location preferences are parked post-beta: users may select cities and broader regions, with AI
mapping such as “Midwest” → Chicago and variable prompt components. Even then, preferences inform/annotate the
write-up rather than becoming match-score quality. The current prompt stays one-size-fits-all. References D-007,
D-020, D-021, D-023, D-036, D-069, D-089, D-090.

### D-094 · Product/compliance · Privacy notice + unsubscribe + account deletion; beta-exit line reduced · accepted · 2026-07-22
Hayden re-scoped the final beta hardening: remaining ledger breadth loses to shipping user-facing features.
**In (a 3-PR block):** PR 1 — a static `/privacy` notice (what's stored; résumé text is processed by
third-party AI model providers — Anthropic + OpenAI — whose API terms exclude training on API data; Resend
delivery; one session cookie; no selling; no auto-apply; deletion path), linked from the landing footer, a
shell footer on non-landing routes, and a disclosure line beside the upload submit. PR 2 — unsubscribe:
`users.digest_paused` (on `users`, not versioned `profiles`, so a reupload can't reset it), a tokenized
no-login link in the digest email footer, and a paused check inside `send_digest`. PR 3 — a `/settings` page
with the pause/resume toggle plus hard account deletion (`DELETE /api/me`: user, profiles, matches, digest
rows; postings/employers untouched — D-009's never-delete covers postings, not user PII). Unsubscribe pauses
digest email only: matching and the dashboard continue. The notice is a plain-language product disclosure,
not legal advice.

**Out (drops D-085 exit-line items):** the five-pillar written scaling assessment, D-086's durable digest
delivery idempotency (the 6h/zero-retry guard covers the observed path), and any monitoring beyond one
platform alert. **Kept minimums:** a single GCP alert policy pair on the nightly Job (execution failed /
no execution in 24h — the one failure tests cannot see), a one-time check that the Google OAuth consent
screen is not in "Testing" mode (100-user hard cap), the July-23 read-only first-Luna-night audit, and the
already-validated no-code employer activations (Hayden-run, not a gate). References D-005, D-009, D-027,
D-037, D-057, D-064, D-082, D-085, D-086, D-090, D-093.

**PR 2 implementation note (2026-07-23, Hayden-decided):** the unsubscribe link is **confirm-page GET +
POST-only state change** (mail scanners prefetch GETs; a prefetch must never unsubscribe anyone), and the
digest also carries the **RFC-8058 one-click pair** (`List-Unsubscribe` + `List-Unsubscribe-Post`) whose
provider POST hits the same endpoint. Token = `itsdangerous.URLSafeSerializer` (already a dependency via
Starlette sessions), **non-expiring**, salt `digest-unsubscribe`, seeded from `VJA_SESSION_SECRET` (now
also mounted on the nightly Job, with `VJA_PUBLIC_BASE_URL`), payload `{uid, email}` — the endpoint
requires both to match the live row (stale-token defense, no user enumeration; invalid → generic 400).
A paused user's `send_digest` returns `paused` before `build_digest`: no verification network cost, no
send, no `digests` row — so the window doesn't advance and a future resume gets the accumulated diff. A
pre-login seed profile (no `users` row) or an unset public base URL ships the email without footer/headers.

**PR 3 implementation note (2026-07-23, Hayden-arbitrated):** the settings surface is **one user
resource** — `GET`/`PATCH`/`DELETE /api/me` (rejected: a separate `/api/settings` path). `GET` now
exposes `digest_paused`; `PATCH {digest_paused}` reuses `set_digest_paused` (404 when the row
vanished concurrently); `DELETE` → 204 and pops the session in-handler (a stale cookie elsewhere
already resolves to 401). Deletion is **one transaction** in child→parent order — matches (by the
user's profile ids) → profiles (**`user_id` OR `user_email`**, catching a never-linked pre-login
seed row) → digests (**by `recipient` email** — the table has no user FK) → the `users` row;
postings/employers/sources are shared corpus and untouched. **The in-flight-backfill race is
accepted, not locked:** FK enforcement means a concurrent `save_match` either commits before the
delete (row removed) or fails after it (one logged traceback aborting a backfill for a
now-deleted profile) — resurrection is impossible; no matching-loop change. `/settings` is
**login-gated only** (a never-onboarded user must still reach deletion; the nav link shows for
every authed user), and the delete confirm is a **plain modal** (Cancel default + red confirm; no
type-to-confirm ceremony). CORS `allow_methods` gains PATCH/DELETE for the dev origin. No
migration — the schema head stays `e91b3a6f2d04`.

### D-095 · Product · Salary display (F2 Phase A) + posting description display · accepted · 2026-07-24
First build off the D-087 post-beta slate. `docs/18` sequences *churn diagnosis → F2 Phase A → F4 → F1 →
F3*; the churn prerequisite blocks **F1 and F4 only**, so salary was buildable now. Hayden added
**description display** to the same session — not in the D-087 slate, and the larger of the two.
Shipped as **two PRs**: salary (no migration) then description (migration + the D-083 pre-merge Neon step).

**The finding that shaped PR 1.** A fill-rate query over the dev DB (314 in-scope open postings) found
`comp_min`/`comp_max` on 172 (55%) and `comp_raw` on 176, with `comp_min` **never** present without
`comp_raw`. But the stored integers are **not display-safe**: despite the extraction prompt already saying
"never annualize hourly compensation", Haiku annualizes — `$49.82 to $60.22 per hour` → `103579/125258`, a
ten-week internship at `$4,250 weekly` → `170000/170000`, `75,000 CAD to 108,00 CAD` → bare integers, and
`Pay within range listed + Bonus + Benefits + Equity` → `81456/122184` whose figures the quoted text never
shows. Rendering those would put a salary on a real posting that the posting never offered — the trust cost
D-008 spends a whole verification pass to avoid.

**Decision: corroboration, not trust.** New pure module `vja.comp` (bottom layer, zero LLM):
`annual_usd_display` formats the integers **only when `comp_raw` agrees they are annual USD**, suppressing
on a non-annual pay period, a non-USD currency, absent/digit-free `comp_raw`, an implausible annual figure,
or an inverted range. The API exposes `comp_min`/`comp_max`/`comp_raw` plus a computed `comp_display`, so
the judgment is server-side and unit-testable and the SPA stays dumb: it renders `comp_display`, else
`comp_raw` verbatim, else "Not listed". The asymmetry is deliberate — a false positive fabricates a salary,
a false negative merely hides a formatted range the raw string still conveys, so ambiguity suppresses.
Against the real dev corpus this displays 157 of 176 comp-bearing rows; all 19 suppressions are correct on
the evidence the row carries (the last-listed case turned out at eval time to be an under-informative
`comp_raw` rather than an invented figure — the posting does quote the range elsewhere — so the guard is
conservative there, and the prompt fix makes such rows display again once re-extracted). `comp_raw` also renders beneath a shown range, because the range is derived and the raw
string is the posting's own wording. The extraction prompt was tightened in the same PR (enumerate the
forbidden periods, forbid non-USD, require the integers to come from `comp_raw`) — future extractions only,
no re-extraction, and the deterministic guard holds with or without it.

**Placement + discoverability (Hayden, this session).** Salary is **panel-only** — no row chip and no sixth
sortable column, because ~45% of rows have no salary and a half-empty column reads worse than a click.
That made the panel's discoverability load-bearing, and the row's most link-looking element (the title
`<a href={apply_url}>` with `stopPropagation`) navigates *away* to the ATS. **Rejected: retargeting the
title to open the panel** — it would remove today's one-click row→ATS jump that beta users already rely on.
Instead: a persistent right-edge chevron that rotates when the row opens (decorative, `aria-hidden` — the
row already carries `role="button"` + `aria-expanded`), the existing `.table-guide` line resharpened to name
what the panel holds, and tour slide 4 copy updated. The `?` nav button already reopens the tour for users
who dismissed it.

**Description (PR 2).** `RawPosting.description` exists but is never persisted — `insert_posting` writes only
`raw_payload`. Rich-list ATSs (iCIMS/Greenhouse/Lever/Ashby/Workable/Pinpoint ≈ 59% of in-scope open) carry
it inside `raw_payload`; the list-only ATSs (Workday/Oracle/SmartRecruiters/Radancy ≈ 41%) fetch it lazily at
extraction via `_DETAIL_RESOLVERS` and **discard it**. Decision: a new `postings.description` column holding
**HTML normalized to plain text** at persist (via `beautifulsoup4`, already a dep from D-052) — no XSS
surface, no new frontend dependency, roughly half the bytes of storing HTML. Filled at insert/update/reopen
from the fetcher and, for list-only ATSs, in `save_extraction` from the detail body already fetched — 100%
coverage going forward at zero new fetch and zero new LLM cost, fill-only-when-NULL so L1 stays authoritative
(the `location`/`source_updated_at` rule, D-043/D-038). **No backfill:** existing rows fill naturally as
content changes, reopens, or re-extracts; a one-shot re-fetch CLI and a clear-`extracted_at` re-extraction
were both rejected as throwaway load and pure LLM cost for text we already had.

**Prompt-change eval (D-093/D-090 gate; run 2026-07-24, real `anthropic/claude-haiku-4-5`, 5 production
payloads from rich-list ATSs, 46,278 in / 2,443 out tokens ≈ $0.06).** Old vs new system prompt, comp fields
only. The weekly internship: old → **212,500** (52 × $4,250 — *worse than the stored 170,000, so the
annualization is not even stable between runs*), new → **null**. The hourly posting: old → 38,460/44,950
(the hourly figures stored as if annual), new → **null**. Both clean-annual controls: **unchanged under both
prompts** — no regression, and the new prompt returns a more faithful verbatim `comp_raw`. The
"Pay within range listed" posting returned 81,456/122,184 under both prompts with `comp_raw` now quoting
"$81,456 - $122,184 per-year-salary" — i.e. that row was never a fabrication, just an under-informative
stored quote. Outputs preserved in the session log. **Hayden signed off on this evidence before merge.**

**PR 2 implementation notes (built 2026-07-24; scope decisions Hayden's, this session).**

*Read path — a detail endpoint, not a list column.* Measured on the dev DB (314 in-scope open): 184 rows
(59%) carry a body, median ~3.2 KB of plain text, p90 5.5 KB. Inlining the full body would take a
tens-of-KB dashboard load past **1 MB** to serve text a user opens on maybe three rows; a truncated
snippet would still add ~380 KB *and* show mostly "About us" boilerplate. So **`GET /api/postings/{id}`**,
fetched when the panel opens, behind the same `_resolve_profile` gate as the list (401 when
`VJA_AUTH_REQUIRED`; the query is floored on the caller's vertical + `in_scope`, so an id from another
vertical 404s rather than leaking). No SPA-side cache — one PK lookup is not worth the state.

*Empty state — render nothing.* With no backfill, most rows have no body on day one. Rejected an
explanatory "not captured yet" line: we're in beta, the rows fill as postings turn over, and the panel
already carries match, salary, and apply.

*Fidelity — block structure survives, inline structure does not.* `vja.text.html_to_text` (new bottom-layer
module) gives paragraphs/headings a blank line, list items one line each, and keeps inline markup on its own
sentence; rendered `white-space: pre-wrap`. Two findings forced its shape: Greenhouse's `content` field is
**escaped** HTML (`&lt;h3&gt;…`), so it is `html.unescape`d before parsing or the user would read raw tags;
and flattening with a newline separator shatters `We use <b>Python</b> and SQL` into one line per fragment,
so the separator is empty and only block tags insert breaks.

*Two invariants the build had to preserve.* (1) **`content_hash` still keys on the fetcher's raw
description** — normalizing before hashing would flip every stored posting's hash on one night, a
corpus-wide false "content changed" plus mass re-extraction (D-088 churn); pinned by a regression test.
(2) **The extraction prompt input is unchanged** — the model still sees the same JSON blob, so results and
the prompt cache don't move; `_source_text` was refactored to `_posting_source`, which reads the payload
**once** and returns both the model text and the body (a second read would double the requests to a
list-only board).

*Write rule.* L1 wins, extraction fills the gap: insert writes the fetcher's body; `update_changed` writes
it unconditionally (a list-only `None` *clears* the stale body, and the `extracted_at` clear in the same
statement guarantees the refill); reopen writes it when present, clears it only when the content changed,
and otherwise preserves it alongside the preserved extraction; `save_extraction` fills only when NULL. Each
list-only fetcher answers `detail_description(payload)` for its own provider shape (new `ListOnlyFetcher`
protocol + `_DETAIL_DESCRIPTIONS` map beside `_DETAIL_RESOLVERS`), so adding a list-only ATS stays a
wire-up. Oracle reads **only** its `External*Str` fields — the payload also carries `Internal*Str` written
for the employee-facing site.

References D-087, D-008, D-005, D-035, D-036, D-038, D-043, D-052, D-080, D-082, D-083, D-088, D-090,
D-093.

### D-096 · Phase 8 · Rippling fetcher + coverage-audit re-rank of the fetcher build order · accepted · 2026-07-26
A read-only audit of prod Neon (182 employers: 145 active, 13 `proposed`, 14 parked `approved`, 10
`retired`) re-triaged the proposal backlog and **found the no-code activation harvest already spent**.
Of D-078's six rows that validated on supported ATSs, **five are now `active`** (ASI, GridBeyond,
CivilGrid, Emerald AI, AiDASH); the sixth (Aloft `#133`) was the deferred judgment call. Live probes of
every remaining `proposed`/`approved` row on a supported ATS: **zero are cleanly activatable** —
Reliable Robotics `#107` (lever `reliable`) and Gridmatic `#126` (lever `gridmatic`) have genuinely
empty boards, Ascend Analytics `#130` 404s on the Greenhouse API (500 on the public board), and Skydio
`#117` has no working Greenhouse slug (`skydio`/`skydioinc`/`skydio1` all 404). The other 19 rows are
blocked on an unsupported ATS or expose none at all. **So adding coverage required building a fetcher,
not running the runbook.**

**Decision 1 — Aloft `#133` → `retired`** (Hayden's call, closing D-078's open item). Its Greenhouse
board is parent **Versaterm's** corporate public-safety board (35 postings, titles like "Chief Services
and Delivery Officer", Ottawa/Mesa); activating it would attribute non-aviation roles to "Aloft" in the
aviation vertical. Stage-A title gating would drop most, but the company attribution would still be wrong.

**Decision 2 — build Rippling next, re-ranking D-078's order.** The three candidates were measured
against live boards rather than trusting the D-078 projection:
- **Rippling — 3 rows (Raptor Maps `#103`, Gridsight `#139`, Portside `#141`), 21 jobs.** Clean
  unauthenticated JSON, single response, real detail endpoint. D-078 filed Rippling as an *opportunistic
  singleton*; this audit promotes it to rank 1.
- **JazzHR — 3 rows (Utilidata `#98`, Near Earth `#118`, uAvionix `#150`), 21 jobs.** No feed at all
  (`/apply/jobs.xml` + `jobs.json` 404, `/apply/feed` 410) — an HTML-parse build like Radancy. Holds
  rank 2; its US in-scope *density* is actually higher, so it is the natural next block.
- **Radancy variants — drops from D-078's rank 2.** The projected "+5, AA is a flagship" does not
  survive probing: **American Airlines and National Grid both 403**, L3Harris's clean JSON endpoint
  returns `results_len=0`, NRG's aria total is a different format (`Results 1 – 10`), and Bombardier
  renders no `searchresults` table. Five targets, five distinct problems.

*Correction on the record:* the audit first reported Rippling at 44 postings. That counted Rippling's
denormalized rows, not jobs (below) — the real figure is 21, which **ties** it with JazzHR. Rippling
still won on contract quality and build risk, not on coverage.

**Decision 3 — the fetcher.** `GET https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs`
(slug-derived) returns a **bare JSON array** holding the complete open set: it ignores
`limit`/`offset`/`page` (a `?limit=5` still returned all 38 rows) and 404s an unknown slug. So it takes
the **single-response false-closure guard** (Workable/Pinpoint/BambooHR, D-049/D-079), *not*
paginate-or-fail — a clean 200 is the complete set, an empty array is a legitimate zero, any error is a
`FetchError`. `external_id = uuid`; `apply_url` is **supplied** (`url`), never constructed;
`location` from `workLocation.label`; **no date in the list** (`createdOn` is detail-only, Pinpoint
precedent). The list omits the body ⇒ **list-only** (D-050): `fetch_detail` is
`…/jobs/{uuid}` and `detail_description` joins the body. The custom-domain endpoint override stays
**Pinpoint-scoped** (D-079) — every Rippling board found lives on the one canonical API host, so a stale
`ats.rippling.com` page URL in an employer row must never be fetched in place of the JSON endpoint.

**Decision 4 — the duplicate-`external_id` guard is narrowed, not waived (amends D-016/D-088).**
Rippling **denormalizes its list: one row per (job × work location)**, so a role open in four cities is
four entries sharing one `uuid`, identical in every field but `workLocation`. Gridsight's 38 rows are
**15 jobs**. The live smoke caught this — the first build failed Gridsight closed under D-088's
"a duplicate `external_id` … is never silently collapsed". That guard was written for *snapshot
completeness defects* (double-fetched pages), not for a provider whose list is a location join. **Ruled
(Hayden):** collapse to one posting per `uuid` and merge the locations — the treatment Workday's
`locationsText` and Oracle's `secondaryLocations` already give a multi-location req — **but only when the
duplicate entries are identical apart from `workLocation`**. Entries sharing a `uuid` that disagree on
*anything else* remain a genuine integrity violation and still fail the whole snapshot with zero
mutation. Rejected: keeping the hard fail (Gridsight permanently unfetchable, dropping Rippling to 2
employers / 6 jobs — at which point JazzHR was the better build), and synthesizing
`external_id = uuid + location` (D-016 forbids synthesized ids, and one opening would become four
dashboard rows and four match rationales — 4× the LLM spend for one real job).
*Implementation note:* the merged location string is **sorted**, because `content_hash` keys on
`location` (`vja.hashing`) — API order would let a reordered board flip every multi-location posting's
hash and fake a corpus-wide content change, the exact churn D-088 exists to prevent.

**Decision 5 — Comply365/Vistair onboards via the curated seed CSV.** D-078 item (5) validated it and it
was never persisted; re-probed at 10 open (BambooHR `vistairhr`, real US software roles). It has never
been in the DB, so it is a *curated seed* row, not a proposal correction — D-077 keeps the CSV reserved
for exactly this. Seed-fetchable aviation 15 → 16.

**Not done here:** `vja-discover` (Hayden runs it himself), and retired Aerovy `#111` (ashby `aerovy`,
2 live Seattle software roles today) is flagged but left retired — reversing a human rejection is his call.

**Status:** built on `feat/rippling-fetcher`. No migration — `ats_type` is a `native_enum=False`
VARCHAR(15) with no CHECK (`db/schema.py`), and `"rippling"` fits, so there is **no Neon pre-merge step**
(D-083). The three proposal activations (`set-ats` → `approve` on `#103`/`#139`/`#141`) must run **after
merge + CD deploy**, or the next nightly logs three failed employers. References D-078, D-077, D-079,
D-050, D-049, D-016, D-088, D-095, D-017, D-070, D-071.

---

### D-097 · Vertical expansion · Trading vertical (fourth, last for now) + narrow cross-vertical employer duplication · accepted · 2026-07-26
**Decision 1 — `trading_software` is the fourth vertical, and the last planned for now.** 44 curated
employers across market makers/prop trading, quant funds, exchanges/market infrastructure, trading
technology, crypto/digital assets, and prediction markets. Scope stays the shared one: **US,
early-career software/data**, same Stage-B knobs as the other three verticals. Built the D-004 way —
seed rows + one YAML + one matching profile, **zero `src/` changes** (`git diff --stat` shows none;
`AtsType` already carried every value the curation needed, including `avature` and `eightfold`).
**36 of 44 (82%) are fetchable today** through existing generic Layer-1 fetchers: 26 Greenhouse, 4 Ashby,
3 Workday, 2 iCIMS, 1 Lever. Two are `detected` on platforms with no fetcher (Two Sigma/Avature,
Millennium/Eightfold) and six are `layer2` (Citadel, Citadel Securities, D. E. Shaw, Bridgewater,
Balyasny, Trading Technologies).

**Decision 2 — the marquee financial-trading firms are duplicated across verticals, not moved.** The
grid/power universe already owned ~17 trading-and-markets employers, curated for their *energy desks*
(D-022). Because a user has exactly one vertical (D-064), a trading user would otherwise see **none** of
the field's most iconic employers. Three options were weighed: curate only net-new firms (robotics'
no-duplication precedent — cheapest, but ships a trading vertical without Jane Street or Citadel);
**move** the pure-financial rows out of grid (grid loses employers it holds for good reason, and prod
needs retire + re-insert surgery under `UNIQUE(vertical, name)`, stranding existing postings); or
**duplicate**. **Ruled (Hayden): duplicate, and only the eight** — Jane Street, Citadel, DRW,
SIG (Susquehanna), Millennium, Balyasny, CME Group, ICE. The **physical merchants stay grid-only**
(Shell, BP, Vitol, Trafigura, Macquarie, Hartree, Freepoint, Castleton, Mercuria, Glencore, EDF Trading,
Koch, Tenaska) — power/gas trading is grid's own thesis, not this vertical's.

A duplicated employer is **two independent rows** keyed on `(vertical, name)` with identical ATS wiring:
separate `employer_id`, separate posting rows, separate diff. Verified end-to-end on a scratch DB —
Jane Street's 221 `external_id`s exist under both rows with no `UNIQUE(employer_id, external_id)`
collision, and a re-sync of the grid row returned **all-`unchanged`** (the D-088 churn check).

**Decision 3 — what that costs, stated honestly (amends the D-005 wording).** D-005's "each ATS endpoint
is hit once per day **total**, regardless of user count" is a rule about *user-count independence* — it
was never a claim about one row per company. Cross-vertical duplication makes it **once per employer
row**: five extra nightly fetches (Jane Street/DRW Greenhouse, SIG/ICE iCIMS, CME Workday; the other
three are `layer2`/`detected` and fetch nothing). An earlier note in this session claimed the duplicated
postings would re-extract for free because extraction is content_hash-cached. **That was wrong and is
corrected here:** `postings_needing_extraction` selects on `extracted_at IS NULL` **per posting row**,
so there is no cross-row reuse of an identical body — the duplicate pays a second Haiku extraction.
Cheap, but not zero.

**Decision 4 — multi-vertical membership as a schema change stays parked.** One employer row belonging
to many verticals (and one fetch feeding both) is the correct long-term shape; robotics already deferred
it to "a separate design PR" and this ADR does not unpark it. Duplication is the interim, and it is
bounded to eight curated rows.

**Curation notes that shaped rows.** Probing beat guessing on nine of them: Optiver's US board is
`optiverus` (the `optiver` board is a near-empty global shell); CTC is `chicagotrading`; Five Rings is
`fiveringsllc`; Headlands `headlandstechnologiesllc`; MarketAxess `marketaxesscorporation`; Galaxy
`galaxydigitalservices`; Kraken's Ashby slug is literally `kraken.com`; Radix splits **campus**
(`radixuniversity`) from **experienced** (`radixexperienced`) boards and the campus board is the one in
scope; Kalshi answers on **both** a stale Greenhouse board (27) and Ashby (36) — the careers site links
Ashby, so Ashby is pinned. **Cboe** is a Phenom front-end over a Workday tenant: both return 64 and
**Workday is pinned** (list-only + paginate-or-fail + a real `postedOn` date). **Hudson River Trading's
only public API is its campus/talent-community Greenhouse board** (3 entries, two of them "join our
talent community" placeholders); it is included because the Stage-A gate drops the two placeholders on
its own — no per-employer rule, no fake postings in a digest (D-008). Excluded for duplicate coverage
(the Jeppesen/Boeing precedent): **Cumberland** rides DRW's board and **Jump Crypto** rides Jump's.
Dropped for want of any locatable careers page: **Squarepoint**. Sell-side bank trading tech and the
market-data incumbents (Goldman/JPM/Bloomberg/Broadridge/FactSet) are **out of the universe** — the big
boards cover them well, and their whole-company boards would swamp the diff for little signal.

**Stage-A tuning, measured not guessed.** Over the 2,871 postings the first real pass fetched, the
shared software/data baseline kept 1,074; the trading vocabulary (`quantitative`, `quant`, `trading`,
`trader`, `algorithmic`, `systematic`, `research`, `low latency`) added **+348**, and `trader` is
deliberately included — excluding it would drop the flagship "Quantitative Trader — New Grad" pipeline a
CS + Econ candidate is a real applicant for. `experienced` was then added to the excludes: trading firms
label their non-campus track literally "Experienced Hire", and it removed **69** survivors, every one
genuinely non-early-career. Final Stage-A share: **1,353 of 2,871 (47%)**, which is a one-time Haiku
extraction backlog of roughly that size when the vertical is imported to prod.

**Status:** built on `feat/trading-vertical`. **No migration** and no `src/` change, so no Neon pre-merge
step (D-083). `main` auto-deploys (D-068) and `/api/verticals` is config-driven, so **the picker offers
Trading & Markets the moment this merges while Neon holds zero trading employers** — the seed import must
follow the deploy promptly. Do **not** run `vja-load-profiles` against prod (it would add a fourth active
profile for the operator's own email). References D-004, D-002, D-005, D-022, D-064, D-016, D-088,
D-008, D-023, D-068, D-083, D-096.

### D-098 · Beta hardening · UI motion: one token set, transitions everywhere, landing scroll reveals · accepted · 2026-07-26
The "the scroll and transition behavior feels clunky" item was scoped from an audit of the real code rather
than the brief's assumptions, and the audit **inverted the premise**. The brief described a Tailwind-shaped
codebase to be de-sludged: strip `transition-all`, kill 300ms hovers, convert `height`/`top` animations off
the layout path. None of that existed. `frontend/` is one hand-written stylesheet (`theme.css`, no Tailwind,
no CSS-in-JS, no inline styles) that contained **five motion declarations in 1433 lines**: zero
`transition-all`, zero animation on a layout property, zero scroll listeners, zero `IntersectionObserver`,
zero `will-change`. The app did not feel clunky because motion was slow. It felt clunky because **30 hover /
focus / checked / selected states were defined and exactly 2 of them transitioned** — everything else,
including the dashboard row's hover background and its 3px verdict spine, flipped at 0ms.

**Scope decisions (Hayden, this session, by questionnaire).** **Transitions go app-wide, not landing-only** —
`.btn`, `.card` and `a:hover` are shared between the marketing page and the app, so scoping to `.landing`
would have meant duplicating rules, and the dashboard row was the worst offender anyway. **The six motion
tokens are the whole vocabulary** (`--ease-out-expo` / `--ease-in-out`, `--dur-fast` 150ms / `--dur-mid`
300ms / `--dur-slow` 700ms, `--reveal-distance` 18px, `--stagger` 70ms); no one-off duration or curve
survives anywhere in the file, including the three pre-existing ones that disagreed with each other
(`120ms ease`, `0.15s ease` written in seconds, `160ms ease-out`). **Scroll reveals are native-first.**

**Built in two merged units.** PR 1 (**#106**) is the foundation: tokens, sixteen base rules given explicit
property lists at `--dur-fast`, the first `:focus-visible` styling in the project's history (it appeared
**zero** times before — every control fell back to a UA outline that is near-unreadable on `#08090c`), and a
global `prefers-reduced-motion` block replacing one that had covered a single property on a single element.
PR 2 is the landing motion: hero on load, everything below the fold on scroll.

**Three engineering judgments worth recording, because each deviates from the obvious implementation.**
(1) **The reveal never hides what it cannot un-hide.** The native path (`animation-timeline: view()` inside
`@supports`) needs no JS at all; the `IntersectionObserver` fallback arms the hidden state by setting
`js-reveal` on `<html>` *only after* it has confirmed an observer exists. A browser with neither path, or
with JS off, renders the finished page rather than a blank one. (2) **`animation-range` ends on `entry`,
not `cover`.** The brief's `entry 10% cover 35%` strands any block near the bottom of the document: once
scrolling stops, a footer can never reach a cover percentage and stays permanently half-faded. `entry 10%
entry 90%` is reachable everywhere. (3) **Reduced motion needs an explicit `animation: none` for the
reveals.** Scroll-driven animations are scrubbed by scroll position, so the global block's
`animation-duration: 0.01ms` does not touch them. The upload spinner is the one deliberate exception to
reduced motion and keeps turning, slower — freezing it would report a hang on a request still in flight.

**Stagger** is `--i` set per item in the markup, read by both paths (`transition-delay` in the fallback,
a per-item `animation-range` start offset natively, since `animation-delay` does nothing on a scroll
timeline). Max index is 4, so the tail lands at 280ms, inside the ~400ms budget. **Above-the-fold hero
content animates on load, never on scroll**, and reveals are applied to section blocks and card grids only.
**No dependency was added** — the whole thing is CSS plus one 48-line hook. Frontend-only, no API contract
moves, no migration. References D-080, D-081, D-042, D-021.

**Amended 2026-07-27 (same decision, two values).** Reviewed live on the deployed landing and the reveals
read as nothing happening. Cause was not amplitude but *when the motion finished*: `entry 90%` completes
while the block is still at the viewport edge, so the whole animation played in peripheral vision. Range now
ends at **`entry 100%`** and `--reveal-distance` goes **18px → 32px**. The mechanism, the two paths, and the
`entry`-not-`cover` rule are unchanged. Also learned and worth writing down: the landing is unreachable while
signed in (`App.tsx` `Root()` redirects an authed user to `/dashboard`), so **landing-only work must be
reviewed logged-out or in a private window** — a signed-in reviewer sees literally none of it.

### D-099 · Beta hardening · Product copy carries no em dashes; back buttons on the non-dashboard pages · accepted · 2026-07-27
Two small usability items from the same session as D-098, both Hayden's calls by questionnaire.

**Em dashes are removed from everything a user reads, and only that.** Scope is **rendered frontend copy
(27 sites) plus the digest email (5 sites in `digest/render.py`)** — the digest is included deliberately
because it is the *primary* surface (D-010), so excluding it would have left em dashes on the thing most
users actually see. **Code comments and docstrings keep theirs** (~58 in the frontend, several hundred
across `src/vja`): cleaning them would be a mechanical diff touching nearly every file in the repo for zero
user-visible gain, and would have swamped review of the motion work it shipped beside.

**Three em dashes are kept on purpose**, in `PostingsTable.tsx:47`, `PostingPanel.tsx:78`, and
`Verdict.tsx:20`. These are not prose — they are the typographic "no value" glyph for a missing location or
an unscored posting. Hayden chose to keep them over an en dash or spelled-out text: they read correctly at a
glance and keep the dense table aligned. **This is why the regression pins are per-page rather than global** —
`Landing` and `Privacy` assert their rendered text contains no `—`, and the digest asserts the same across
its text, HTML, and subject, but the dashboard components legitimately still contain one.

**Digest separators.** `Company — Title (Location)` becomes **`Company · Title (Location)`**, and the apply
link's separator moves to `·` as well, reusing the middot the same file already uses for `[verdict · score]`
rather than inventing a second idiom. Closure rollups go to `Company: N` in both the text and HTML bodies,
where a colon reads more naturally before a count than a middot would. The email's structure, the D-056
rollup thresholds, and the subject line are all untouched.

**Back buttons on Settings and Privacy both point at `/`, not `/dashboard`.** This is the non-obvious part:
`/settings` is **login-gated only** (D-094), so a signed-in user who has not onboarded can reach it, and for
them `/dashboard` bounces onward to `/onboarding`. `/` is the smart root (D-065) and is the single target
that routes a profiled user, an unprofiled user, and a logged-out visitor each to the right place. Privacy's
uses a **plain `<a>`, not a Router `<Link>`**, preserving that page's existing Router-free property — it has
to render for logged-out visitors, and its test renders it with no `MemoryRouter` at all. `/upload`'s
existing back link still points at `/dashboard`, correctly: that route is already profile-gated, so the
ambiguity does not arise there. References D-094, D-065, D-010, D-056, D-098, D-021.
