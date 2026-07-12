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
  `nightly` → `pipeline`/`extract`/`match`/`digest`/`discover` → `fetchers`/`verticals` → `db` →
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
  by `content_hash`; match prompts are prompt-cached; matching is eval-gated. Sonnet matching runs at
  **`effort=medium`** (env-overridable `VJA_MATCH_EFFORT`; the lowest eval-passing effort — `high` overspends
  since thinking bills as output), not the API default `high`. (D-035, D-036, D-069)
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
  stays `vja`) consuming `GET /api/postings`. **`react-router-dom` routes**, all guarded off `useAuth()`
  (D-065): `/` (smart root: logged-out → `Landing`, no-profile → `/onboarding`, has-profile → `/dashboard`),
  `/login`, `/onboarding` (pick vertical + upload), `/dashboard` (their vertical), `/upload` (résumé update,
  vertical locked); `App.tsx` is the shell + auth-aware nav, pages live in `frontend/src/pages/`. **Every fetch
  is credentialed** (`credentials: "include"`) so the session cookie resolves the authed user's profile
  server-side (D-055). Dev = Vite dev server + CORS (`VJA_CORS_ORIGINS`, default `:5173`); prod = FastAPI
  serves the built SPA same-origin from `frontend_dist_dir()` — `VJA_FRONTEND_DIST` (set to
  `/app/frontend/dist` in the container, where the non-editable install moves the package off the repo
  layout) or the repo-layout default (a catch-all → `index.html` keeps deep-links/hard-refreshes off a 404;
  mount gated on a real `index.html`, D-059/D-060). **One vertical per user (D-064):** the SPA routes each user
  to *their own* vertical via **`GET /api/me`** (`{user, profile|null}`), never a cross-user picker; the
  dashboard never renders logged-out (killing the old 401-as-error leak). `GET /api/verticals` remains **only**
  the onboarding picker's source and is now **config-driven** (`available_verticals()`, joinable even with zero
  profiles — the B-4 fix), not active-profile-driven. **Prod ships as one multi-stage image** (`Dockerfile`; SPA
  built in a `node` stage, package `uv sync --no-editable` into a `uv` runtime) with **two run targets**:
  `vja-api` (Cloud Run service) + `vja-nightly` (Cloud Run Job, entrypoint override) — no second build. (D-042,
  D-058, D-059, D-060, D-064, D-065)
- **Résumé upload is the SPA's only write surface** (`/onboarding` picks vertical + uploads; `/upload` re-uploads
  with the vertical **locked** to theirs — both soft-gated by login → `/login`; the POST is hard-gated by
  `require_user`). On success the SPA **refreshes `/api/me`** (so the new profile lands before routing) then
  navigates to `/dashboard`; the matched view shows a **bounded client-side poll** (`~10s × ~2.5min`) of the
  backfill — no backend push/status endpoint (honours D-057) — then falls back to "full results after tonight's
  run". Guard responses (401/413/422/429/404 + **409 second-vertical**) surface a typed `ApiError`. (D-058,
  D-057, D-065)

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
  v1). The dashboard shows *that* user's vertical (resolved via `/api/me` → `active_profile_for_user`) — there is
  **no cross-user vertical picker**. **Enforced** at the write path: `POST /api/profiles` **409s** a second
  vertical for an already-onboarded user; re-upload of the *same* vertical stays an idempotent résumé update.
  (Enforced in the endpoint, not `upsert_profile`, so the CLI/seed loader stays unconstrained.) (D-064, D-065)
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
  hash; meter LLM spend. **Metering is real, not a proxy:** every LLM call's `TokenUsage`
  (input/output/cache_read/cache_write) is summed per stage and **persisted to `pipeline_runs`**
  (four token columns) + logged as a per-stage nightly line with the matching cache-hit %. The
  `$0.01`-per-match figure survives **only** as the backfill budget-guard proxy (below), not as the spend
  meter. (D-035, D-036, D-069)
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
- **`main` auto-deploys to prod** — the `deploy` job in `ci.yml` runs after every gate is green
  (`needs: [gates, postgres, frontend, secrets]`, push-to-`main`/`workflow_dispatch` only), auths to GCP via
  **keyless Workload Identity Federation** (no SA key in the repo; `GCP_WIF_PROVIDER`/`GCP_DEPLOY_SA` are repo
  *variables*), then execs **`ship.sh --force`** — one code path, so the guards-preserved prod config never
  drifts into YAML. CD sets `ROLLBACK_ON_SMOKE_FAIL=1` (auto-roll traffic to the prior revision on a failed
  smoke). **Migrations stay manual:** CD deploys code only — run `alembic upgrade head` on Neon *before* merging
  a schema-changing PR. `ship.sh` is still the manual break-glass. (D-068, D-066, D-025)
- **Frontend gate = eslint + `tsc --noEmit` + vitest** (Vitest + React Testing Library), run
  in the inner loop and path-filtered (pre-commit hook + a CI `frontend` job). The dashboard's
  own behavior is pinned here; the B1 API contract stays pinned by the Python API tests. (D-042)

## Coverage / fetchers

- **Fetcher build order:** Greenhouse/Lever/Ashby → Workday → Tier-B (**iCIMS + Workable +
  SmartRecruiters + Oracle + Paylocity done**) → Tier-C (**Radancy + Phenom done**) →
  **BambooHR done** → **demand-ranked next (D-076): JazzHR probe/singletons** → Layer-2 LLM-read for the
  custom tail + HN/niche. The discovery-demand
  ledger in `docs/07` feeds this ranking. **Probe the multi-tenant platforms for a clean API before the
  generic LLM-read** — the tail is mostly JS/bot-blocked, so a literal LLM-read-the-page has near-zero
  reach; route to a platform fetcher where one fits (D-017), Layer 2 for the rest. (D-018, D-048,
  D-049, D-050, D-051, D-052, D-076)
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
- **Paylocity fetcher targets the server-rendered tenant listing whose `window.pageData.Jobs` is the complete
  set.** Explicit per-tenant UUID/name endpoint; single-response false-closure guard; `external_id = JobId`;
  `apply_url` constructed as `/Recruiting/jobs/Apply/{JobId}`; description lazily fetched from the public detail
  page. The empty v2 feed is not a data path. (D-076)
- **Phenom fetcher targets the public `POST {tenant}/widgets` API.** Explicit tenant base with required
  `lang`/`country` query config; `refineSearch` paginates by `from`/`size` and must exactly reach stable
  `totalHits`; `external_id = jobId`; inline apply/location/date; `jobDetail` accepts that stable id and lazily
  returns the full job. No tenant values live in code. (D-076)
- **BambooHR fetcher targets slug-derived `GET https://{slug}.bamboohr.com/careers/list`.** The
  `meta.totalCount`-anchored response is single and authoritative (valid zero closes cleanly; malformed or
  incomplete shapes fail closed); `external_id = id`; title is trimmed; public apply URL is constructed;
  structured `atsLocation` wins over `location`/remote fallbacks. Description is lazily resolved from
  `/careers/{id}/detail`, returning only `result.jobOpening` and never application `formFields`. (D-076)
- **List-only ATSs' description is a lazy detail fetch, routed by `extract._DETAIL_RESOLVERS`**
  (Workday + SmartRecruiters + Oracle + Radancy + Paylocity + Phenom + BambooHR) — fetched only for in-scope
  survivors (cost discipline); every other ATS carries the description in `raw_payload`. Adding a
  list-only ATS is a one-line map entry, no per-company branching. (D-050, D-051, D-052, D-076)
- **Grid/power (energy) is the first-built, seeded/verified vertical;** aviation is the
  Week-4 architecture test — **shipped config-only in Phase 7 (D-046)**. (D-022, D-002, D-046)

## Discovery (Layer 3)

- **The discovery agent finds new *employers*, never postings, and only ever writes `proposed`
  rows.** Weekly (thin core is on-demand via `vja-discover`), **GPT-5.6 Terra** by default
  (`VJA_DISCOVER_MODEL`; only priced 5.6 Sol/Terra/Luna models are accepted) runs three sequential,
  separately bounded waves: capital portfolios, industry lists, and market adjacency. Every proposal
  is **validated by actually fetching** —
  the matching registry fetcher must return ≥1 posting (D-017 reuse) → `proposed`/`detected`; else
  `proposed`/`unknown`/`layer2` for manual triage. Rows are `source=agent_discovered`,
  `status=proposed`, idempotent on `UNIQUE(vertical, name)`; **only `active` employers are fetched
  nightly**, so proposals sit inert until a human approves them (**human approval is the rule at
  first**). (D-070, D-047, D-017, D-005)
- **Discovery and ATS resolution are separately bounded and incrementally checkpointed.** Each of
  three research waves gets at most **5** hosted web actions; at most **5** deduped candidates proceed,
  and each unresolved candidate gets at most **4** more actions (low reasoning, 2k output, 120s).
  Resolution requires a canonical provider URL plus slug/endpoint and derives “supported” from the
  fetcher registry, never the model's label. Confirmed-but-unsupported or failed validation stays
  `unknown`/`layer2`, with typed outcome + evidence in `notes`. `VJA_DISCOVER_MAX_USD` defaults to **$4**
  and includes model-aware tokens, cache pricing, and $0.01 billable search actions; no new paid wave
  or resolver starts after crossing it, but one bounded tool-free structuring call preserves completed
  work. One rolling report is updated after every wave/resolver. (D-074, D-073, D-070)
- **Proposals are promoted through `vja-review` (approve/reject/list) — the human gate.** `approve`
  → `active` if the proposal's `ats_type ∈ SUPPORTED_ATS_TYPES` (fetched next nightly), else →
  `approved` and **parked** (vetted, no Layer-1 fetcher yet). `reject` → `retired` (never deleted,
  D-009). Fetchability is keyed on `SUPPORTED_ATS_TYPES` (the nightly's own predicate), **not**
  `verification`, so fixing a row's `ats_type` and approving it activates it. `approved`/parked rows
  are **structurally unfetchable** — `active_fetchable_employers` filters on `status=active` AND a
  supported ATS — so `list --status approved` is the parked-queue flag, no runtime guard needed.
  (D-071)
- **Proposal corrections go through `vja-review`, never raw SQL on prod and never the seed CSV** (CSV +
  `vja-import-employers` is reserved for *curated seed* rows). `set-ats` stamps
  `ats_type`/`ats_slug`/`endpoint` **only after a successful registry fetch** (≥1 posting
  — the same D-070 gate the agent is held to) and never touches `status`; `approve` stays the only
  promotion gate and must also promote **parked** rows whose ATS became fetchable. The new-fetcher
  activation sweep is a composed runbook (`list --provider` → `set-ats` → `approve`, docs/14), not a
  batch command. (D-077)
- **The weekly discovery schedule is ready-but-OFF.** `vja-discover` stays a manual command until its
  live per-run cost is measured; the launchd template (`com.vja.discover.plist.template`, not
  auto-installed) + Cloud Scheduler runbook (CUTOVER §8b, not created) exist but are disabled. The
  trigger is swappable config, not code (D-031). (D-071)
