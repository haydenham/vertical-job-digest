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
- **A closed posting that reappears is reopened in place, never re-inserted** — `sync_employer`
  routes a `diff.new` id that matches `closed_index` to `reopen_posting` (UPDATE the surviving row,
  not `INSERT` — which would violate `UNIQUE(employer_id, external_id)`). The reopen resets
  `first_seen_at`, so the role **re-enters the `new` set** (surfaces as new again); it re-extracts
  only if the body's `content_hash` moved. (D-053, D-009)
- **DB access = SQLAlchemy Core + Alembic.** SQLite now → Postgres at first hosted deploy
  (`alembic upgrade`, URL swap). The Postgres path is **CI-verified on both dialects** — the default
  suite re-runs on a `postgres:16` service via `VJA_TEST_DATABASE_URL`, so the cutover is a proven URL
  swap and later tables are born-on-Postgres-verified. **Every engine sets `pool_pre_ping=True`; the hosted
  PG path also sets `pool_recycle=1800`** so Neon's serverless autosuspend can't hand out a dead connection
  (`src/vja/db/engine.py`). (D-025, D-054, D-062)
- **Migrations run with SQLite foreign keys OFF** (`migrations/env.py`, set at connect; the app's runtime
  engine keeps them ON). A batch table-rebuild (SQLite's only way to add a FK to an existing table) drops +
  recreates the table, which trips any *referencing* table (`matches → profiles`) on a populated DB unless
  FKs are off — exactly SQLite's documented ALTER procedure. Pinned by a populated-DB regression test. (D-055)

## Digest & delivery

- **Verification before digest:** every apply link must resolve before a posting ships.
  One fake posting costs more trust than ten real ones earn. (D-008)
- **Digest recipient is the matched profile's `user_email`.** `VJA_DIGEST_RECIPIENT` is the
  **ops/alert** recipient (failure alerts), NOT the digest recipient. (D-027, D-037)
- **Empty digest = skip send:** no email, no `digests` row. (D-028)
- **Closures roll up by company above 10 in the digest body** — ≤10 enumerate per role, >10 render
  `N roles across C companies` + top-10 + "…and M more". Subject keeps the true count and the audit
  blob keeps the full closed list; only the human-facing body summarizes. (D-056)
- **Email digest (push) is primary; the dashboard (pull) is read-only** over the same
  nightly-computed data — no live fetching. (D-010)
- **The dashboard is a Vite/React/TS SPA in `frontend/`** (user-facing brand **Rolefeed**; the codebase
  stays `vja`) consuming `GET /api/postings`. **`react-router-dom` routes** `/` (dashboard), `/login`,
  `/upload`; `App.tsx` is the shell + auth-aware nav, pages live in `frontend/src/pages/`. **Every fetch is
  credentialed** (`credentials: "include"`) so the session cookie resolves the authed user's profile
  server-side (D-055). Dev = Vite dev server + CORS (`VJA_CORS_ORIGINS`, default `:5173`); prod = FastAPI
  serves the built SPA same-origin from `frontend_dist_dir()` — `VJA_FRONTEND_DIST` (set to
  `/app/frontend/dist` in the container, where the non-editable install moves the package off the repo
  layout) or the repo-layout default (a catch-all → `index.html` keeps deep-links/hard-refreshes off a 404;
  mount gated on a real `index.html`, D-059/D-060). **One vertical per user (D-064):** the SPA routes each user
  to *their own* vertical (via `/api/me`), not a cross-user picker. *⚠ Known defect being fixed: the currently
  **deployed** build still uses a global `GET /api/verticals` picker defaulting to the sorted-first vertical, so
  other-vertical users 404 — the onboarding overhaul (D-065, `docs/13` Phase B) is the fix.* **Prod ships as one
  multi-stage image** (`Dockerfile`; SPA built in
  a `node` stage, package `uv sync --no-editable` into a `uv` runtime) with **two run targets**: `vja-api`
  (Cloud Run service) + `vja-nightly` (Cloud Run Job, entrypoint override) — no second build. (D-042, D-058,
  D-059, D-060)
- **Résumé upload is the SPA's only write surface** (`/upload`, soft-gated by login → `/login`; the POST is
  hard-gated by `require_user`). On 202 the UI is optimistic — "matching runs in the background", no status
  polling (honours D-057's no-status-endpoint); guard responses (401/413/422/429/404) surface a typed
  `ApiError`. (D-058, D-057)

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
- **Signup backfill caps at 5 days, `trigger=backfill`, idempotent** — and at
  `VJA_BACKFILL_MAX_POSTINGS` candidates (D-057, the cost guard). *(Supersedes D-024's original
  2-week cap.)* The nightly match is NOT capped (neither by date nor count); the dashboard's 14-day
  toggle is decoupled from the backfill window. (D-039, D-057, amending D-024)

## Auth & identity

- **A user is a `users` row** (`google_sub`, `email`, `name`), created at first **Google OAuth (OIDC)**
  login. **Identity still anchors on email** (D-027): `upsert_user_by_google` adopts a pre-existing
  email-only row and **backfills `profiles.user_id` by email**, so the seed profile attaches on first
  login with no data migration. `profiles.user_email` is retained (match/digest recipient unchanged). (D-055)
- **One vertical per user (policy — D-064).** A user has exactly **one** active profile, in **one** vertical,
  chosen **once at signup** and **immutable** (changing verticals = a manual/support action, out of scope for
  v1). The dashboard shows *that* user's vertical — there is **no cross-user vertical picker**; the write path
  rejects a second vertical. *This was always policy but undocumented → the deployed SPA violates it (global
  picker → 404); fix = the D-065 onboarding overhaul (`docs/13` Phase B).* (D-064)
- **Login is Authlib OIDC → a signed-cookie session** (`SessionMiddleware`, secret `VJA_SESSION_SECRET`).
  Login routes are **inert (503) until `GOOGLE_CLIENT_*` are set**; the real Google round-trip is a manual
  check, the suite mocks the token exchange. Cookie hardening (`Secure` via `VJA_COOKIE_SECURE`, `SameSite=Lax`,
  `max_age`) + the HTTPS callback URI (`VJA_PUBLIC_BASE_URL`, else proxy-header-aware `url_for`) are **built and
  env-gated** (D-059); the actual prod flips + redirect-URI registration land at the deploy (9.5c/d). (D-055, D-059)
- **The read API resolves the profile from the authenticated user** (the docs/11 §2 seam): authed → *that
  user's* profile for the vertical, another user's `profile_id` → 403; unauthenticated → the single-active
  default. **Hard enforcement is gated by `VJA_AUTH_REQUIRED`** — on ⇒ no session is 401. **Now ON in prod**
  (flipped at the 9.5d go-live, D-067): anonymous `/api/postings` → 401; the dashboard requires login. (Default
  stays off for local dev/tests; it was off through 9.4, not re-architected.) (D-055, D-005, D-058, D-067)
- **Secrets are env-only** (`GOOGLE_CLIENT_ID/SECRET`, `VJA_SESSION_SECRET`), never in the repo — a
  platform secret store is a config swap. (core, D-055)
- **Résumé upload is the first write endpoint:** `POST /api/profiles` (multipart), behind
  `require_user` (401 without a session). It runs the D-033 adapter (`vja.resume`, text/markdown +
  text PDF; scanned/empty/non-text → 422; PII text never logged) → `upsert_profile` (which now stamps
  `user_id` at creation, the D-055 link at upload not just login) → a **background** `run_backfill`,
  returning 202. The read API stays read-only (D-005); this write path is the sole exception. (D-057)

## Cost & safety

- **Cost discipline from day one:** LLM only where structure runs out; cache by content
  hash; meter LLM spend. (D-035, D-036)
- **Signup backfill is guarded by a per-backfill cap + a global daily ceiling.** The cap
  (`VJA_BACKFILL_MAX_POSTINGS`, default 100) bounds one signup's candidate set inside `run_backfill`
  (nightly is uncapped); the ceiling (`VJA_DAILY_LLM_BUDGET_USD`, default $5) refuses a backfill
  (429) once today's *estimated* spend (`count_matches_since(midnight) × ~$0.01`, a proxy — there's
  no per-match ledger) is reached. Captcha / email-verify / edge rate-limiting are deferred to the
  9.5 deploy (OAuth already bounds abuse to real accounts). (D-057)
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

- **Fetcher build order:** Greenhouse/Lever/Ashby → Workday → Tier-B (**iCIMS + Workable +
  SmartRecruiters + Oracle done**) → Tier-C platform fetchers (**Radancy done; Phenom next**) →
  Layer-2 LLM-read for the custom tail + HN/niche. **Probe the multi-tenant platforms for a clean API
  before the generic LLM-read** — the tail is mostly JS/bot-blocked, so a literal LLM-read-the-page has
  near-zero reach; route to a platform fetcher where one fits (D-017), Layer 2 for the rest. (D-018,
  D-048, D-049, D-050, D-051, D-052)
- **Workday `cxs` fetcher is list-only + paginate-or-fail;** `osv-` Workday hosts route to
  Layer 2; a tenant board exceeding Workday's ~4000 offset cap also routes to Layer 2
  (paginate-or-fail rejects the truncated page — RTX, D-046). (D-032, D-046)
- **iCIMS fetcher targets the Career Sites (Jibe) `GET {careers_base}/api/jobs` JSON API, not the
  legacy portal.** One generic fetcher (uniform payload across tenants); paginate-or-fail; rich list
  (`apply_url` + full `description` + ISO `update_date`, no detail fetch). Legacy-portal / non-Jibe /
  auth-gated iCIMS tenants route to Layer 2. (D-048)
- **Workable fetcher targets the embed-widget API** (`apply.workable.com/api/v1/widget/accounts/{slug}?details=true`,
  slug-derived). **Single response, not paginated** → the Greenhouse/Lever single-request false-closure guard
  (a clean 200 is the complete set; empty `jobs` = legitimate 0 open; any error → `FetchError`), not
  paginate-or-fail. Rich list: `apply_url`/`description`/`updated_at` inline, no detail fetch.
  `external_id = shortcode`. (D-049)
- **SmartRecruiters fetcher targets the public postings API** (`api.smartrecruiters.com/v1/companies/{slug}/postings`,
  slug-derived; limit/offset added per page). **List-only + paginate-or-fail** on `totalFound`; the list omits the
  description + apply URL → `apply_url` is **constructed** (`jobs.smartrecruiters.com/{slug}/{id}`) and the description
  is a lazy `fetch_detail` (Workday parity, D-032). `external_id = id`; `location` from `fullLocation` (empty
  comma-segments collapsed); `updated_at = releasedDate`. (D-050)
- **Oracle HCM/ORC fetcher targets the Candidate-Experience REST API** (`{host}/hcmRestApi/resources/latest/
  recruitingCEJobRequisitions?...&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber={CX_n}`;
  **explicit per-tenant endpoint**, the `expand` is required). **List-only + paginate-or-fail** on `TotalJobsCount`
  (limit/offset are `finder` sub-params); `apply_url` **constructed** (`{careers_url}/job/{Id}`), description a lazy
  `fetch_detail` (host + siteNumber parsed off the list endpoint). `external_id = Id`; `location = PrimaryLocation`;
  `updated_at = PostedDate`. Per-tenant hosts not yet found (Honeywell/Con Edison) route to Layer 2. (D-051)
- **Radancy/TalentBrew fetcher targets the server-rendered `GET {endpoint}/search-jobs/results` HTML, not the
  JS landing page.** The repo's first **HTML-parse** fetcher (`beautifulsoup4`); one generic per-platform parser of
  the uniform `<table id="searchresults">` markup. **List-only + paginate-or-fail** on the table `aria-label` total
  ("Results 1 to 25 of N"), pages by `CurrentPage`; description is a lazy `fetch_detail` (`div.jobdescription`).
  `external_id` = the `/job/{slug}/{id}` **path** (Workday `externalPath` parity — the detail URL needs the slug;
  the id alone 404s); `apply_url` is that path absolute; `updated_at` from the `jobDate` cell. Endpoint is
  **explicit per-tenant** (not slug-derived). (D-052)
- **List-only ATSs' description is a lazy detail fetch, routed by `extract._DETAIL_RESOLVERS`** (Workday +
  SmartRecruiters + Oracle + Radancy) — fetched only for in-scope survivors (cost discipline); every other ATS carries
  the description in `raw_payload`. Adding a list-only ATS is a one-line map entry, no per-company branching. (D-050,
  D-051, D-052)
- **Grid/power (energy) is the first-built, seeded/verified vertical;** aviation is the
  Week-4 architecture test — **shipped config-only in Phase 7 (D-046)**. (D-022, D-002, D-046)
