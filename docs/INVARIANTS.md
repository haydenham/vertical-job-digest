# INVARIANTS — the rules that are true *right now*

**What this is.** A derived, always-current registry of the cross-cutting rules that
govern this system. Read it before any change; it is the fastest way for a human or an
agent to avoid acting on a stale or half-remembered rule.

**What this is NOT.** It is not the decision history. `DECISIONS.md` is the immutable,
append-only log of *why* and *when* we decided things; this file is the *what's true
today* view on top of it. When they ever disagree, an ADR was superseded and this file
was not updated — fix this file. Authority order is unchanged: build specs (`docs/04+`)
> `CLAUDE.md` > planning memos.

**How to maintain it.** When an ADR changes a live rule, edit the affected line here in
the same session — don't append, *replace*. Keep each rule to one line with its backing
ADR(s) in parentheses. If a rule here has no ADR, it's a core principle from `CLAUDE.md`.

---

## Architecture & code structure

- **Layered imports: lower layers must not import higher ones.** The stack, top→bottom:
  `nightly` → `pipeline`/`extract`/`match`/`digest` → `fetchers`/`verticals` → `db` →
  `prefilter`/`scope`/`dates`/`diff`/`hashing` → `models`. **Machine-enforced** by
  `import-linter` (`uv run lint-imports`; pre-commit + CI). `models` imports nothing.
  *One grandfathered back-edge:* `db.employers → fetchers.registry` (see `pyproject.toml`).
- **Nothing vertical-specific in code.** A vertical = config (employer list, sources,
  matching profile). Adding a vertical must cost only curation + config; any forced code
  change is a defect. (D-004; **proven** by the Phase-7 aviation add — shipped config-only
  end-to-end, D-046)
- **No per-company scrapers.** Route each employer to a generic platform fetcher; if none
  fits, it's Layer 2 — never a bespoke scraper. (D-017)

## Execution & pipeline

- **All fetching, API keys, and LLM calls run server-side in the nightly pipeline.** Users
  only read precomputed DB results. Each ATS endpoint is hit once per day total,
  regardless of user count. (D-005)
- **Pipeline order is fetch → diff → extract → match → verify → send.** (D-003, D-005)
- **The nightly job is `vja-nightly`** (one process: run → extract → match → digest per
  profile, alert on hard failure). `vja-run`/`vja-extract`/`vja-match`/`vja-digest` are
  debugging entry points. The scheduler (launchd) is a swappable trigger, not code — the
  cloud cutover swaps it. (D-031)
- **Every pipeline run writes a `pipeline_runs` summary; per-fetcher failures isolate** and
  alert loudly rather than aborting the run. A digest that fails to send is itself an alert.

## Matching & extraction

- **Matching is push, not pull:** nightly batch over (new posting, active resume) pairs.
  On-demand matching exists for exactly three cases: signup backfill, resume update
  (re-match, store `resume_version`), per-posting deep-dive (later). (D-006)
- **Two cheap gates precede the strong model.** Stage A: free config-driven whole-word
  keyword scope gate on the title, computed on the fly (drops out-of-scope before any LLM
  cost). Stage B: cheap level/location/work-auth pre-filter deciding who earns the
  rationale model; an explicit non-US country name beats a colliding US state code (e.g.
  "IN"=India/Indiana). Stage A∧B is **persisted as `postings.in_scope`** at extraction so
  the dashboard can floor on it. (D-023, D-034, D-036, D-043, D-044)
- **Extracted `location` is L1-authoritative.** The fetcher's structured location (e.g. Workday
  `locationsText`) is set at insert; extraction fills `location` only when it's still NULL and
  never overwrites a non-null L1 value (mirrors `source_updated_at`, D-038). (D-043)
- **Matching is reasoning, not similarity.** Every rationale must state fits, gaps, and a
  verdict + score. Willingness to say *no* is a product requirement. (D-007, D-036)
- **Model tiering:** Haiku for extraction, Sonnet for match rationale. Extraction is cached
  by `content_hash`; match prompts are prompt-cached; matching is eval-gated. (D-035, D-036)
- **Resume input abstracts to `resume_text`;** non-text formats are a signup-time adapter,
  not pipeline concern. (D-033)

## Diff & data model

- **The diff is the product.** Never show stale listing walls; show what changed. (D-009)
- **Diff identity is the ATS `external_id`, never fuzzy title-match.** (D-016)
- **Vanished postings are marked `closed`, never deleted** — death detection keeps dead
  links out of the digest and yields lifespan stats. (D-009)
- **DB access = SQLAlchemy Core + Alembic.** SQLite now → Postgres at first hosted deploy
  (`alembic upgrade`, URL swap). (D-025)

## Digest & delivery

- **Verification before digest:** every apply link must resolve before a posting ships.
  One fake posting costs more trust than ten real ones earn. (D-008)
- **Digest recipient is the matched profile's `user_email`.** `VJA_DIGEST_RECIPIENT` is the
  **ops/alert** recipient (failure alerts), NOT the digest recipient. (D-027, D-037)
- **Empty digest = skip send:** no email, no `digests` row. (D-028)
- **Email digest (push) is primary; the dashboard (pull) is read-only** over the same
  nightly-computed data — no live fetching. (D-010)
- **The dashboard is a Vite/React/TS SPA in `frontend/`** consuming `GET /api/postings`. Dev =
  Vite dev server + CORS (`VJA_CORS_ORIGINS`, default `:5173`); prod = FastAPI serves the built
  `frontend/dist` same-origin via StaticFiles. The frontend never hardcodes a vertical —
  `GET /api/verticals` drives the picker. (D-042)

## Dashboard & freshness

- **Dashboard universe = the persisted in-scope set, never raw open.** The query floors on
  `postings.in_scope IS TRUE` (the durable Stage-A+B marker, stamped at extraction from
  `passes_prefilter`), so out-of-scope *and* out-of-US/level roles never surface. "Full open set"
  means the *in-scope* open set. (D-041, D-043)
- **Dashboard = single Matched/Cleaned view.** `view` ∈ {`matched` (default — this résumé's relevant
  verdicts only, the AI recommendation subset), `cleaned` (the whole in-scope US-software universe —
  **every** verdict incl. `no` and not-yet-assessed; the objective job list, same set for any
  profile)}. `no` is hidden from *Matched* + the digest (D-037) but **shown in Cleaned** (D-045).
  Orthogonal *recency* axis: `window` ∈ {new_today, week, two_weeks, all} (default all). Match quality
  is a LEFT JOIN on `(profile_id, resume_version)` via `open_postings_with_match_quality`.
  *(Supersedes D-041's additive toggles; amends D-043's "rejected never shown.")* (D-045, D-043, D-037)
- **Relevant verdicts = `models.RELEVANT_VERDICTS`** (strong_yes/yes/maybe) — one home, shared by
  the digest's `new` set and the dashboard's matched default. (D-037, D-041)
- **The dashboard never triggers a match** (read-only, D-005), so its window has zero LLM cost —
  the 5-day cap governs only the signup backfill, decoupled from the dashboard window. (D-041, D-039)
- **Recency windows key on the ATS posted/updated date:** `COALESCE(source_updated_at,
  first_seen_at) >= cutoff`. Toggles: *new today* / *within 1wk* / *within 2wk* / *all
  open*. (D-030, D-024, D-038, D-039)
- **"New today" uses `first_seen_at` (midnight UTC)** so it equals the digest, not the ATS
  date. (D-030, D-039)
- **Signup backfill caps at 5 days, `trigger=backfill`, idempotent.** *(Supersedes D-024's
  original 2-week cap.)* The nightly match is NOT capped; the dashboard's 14-day toggle is
  decoupled from the backfill window. (D-039, amending D-024)

## Cost & safety

- **Cost discipline from day one:** LLM only where structure runs out; cache by content
  hash; meter LLM spend. (D-035, D-036)
- **No auto-apply.** The tool surfaces and reasons; it never submits applications. (core)
- **Politeness is policy:** rate limits, sane user agent, respect robots.txt on the long
  tail. Getting IP-banned is a self-inflicted coverage hole. (core)
- **API keys in env only, never in the repo; DB never publicly exposed.** A git-ignored
  `.env` is auto-loaded. (core)

## Testing & workflow

- **Testing is policy, not preference** (this code is model-written): no behavior is done
  until a test pins it at the right level; bug fixes start with a failing regression test.
  (D-021)
- **Default `pytest` suite is fast/offline/free** (unit + integration + system). `live` /
  `e2e` / `eval` are opt-in markers; tests run against captured fixtures, not live ATS.
  LLM evals are a path-filtered CI merge gate. (D-019, D-020)
- **Definition of Done:** green tests + ruff/format/mypy + import-linter + a human-read
  diff + updated docs, before merge. CI and pre-commit run the same checks. (D-021)
- **Toolchain is `uv`; the lockfile must stay in sync** (`uv lock --check` in CI). (D-014)
- **Frontend gate = eslint + `tsc --noEmit` + vitest** (Vitest + React Testing Library), run
  in the inner loop and path-filtered (pre-commit hook + a CI `frontend` job). The dashboard's
  own behavior is pinned here; the B1 API contract stays pinned by the Python API tests. (D-042)

## Coverage / fetchers

- **Fetcher build order:** Greenhouse/Lever/Ashby → Workday → Tier-B (iCIMS/Workable/
  Oracle/SmartRecruiters) → Layer-2 LLM-read for the custom tail + HN/niche. (D-018)
- **Workday `cxs` fetcher is list-only + paginate-or-fail;** `osv-` Workday hosts route to
  Layer 2; a tenant board exceeding Workday's ~4000 offset cap also routes to Layer 2
  (paginate-or-fail rejects the truncated page — RTX, D-046). (D-032, D-046)
- **Grid/power (energy) is the first-built, seeded/verified vertical;** aviation is the
  Week-4 architecture test — **shipped config-only in Phase 7 (D-046)**. (D-022, D-002, D-046)
