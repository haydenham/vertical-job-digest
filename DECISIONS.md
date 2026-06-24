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
