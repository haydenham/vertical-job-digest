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
