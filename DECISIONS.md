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
