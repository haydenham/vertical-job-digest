# ATS Routing & Fetcher Build Priority

*Output of the ATS-identification pass (2026-06-11) over the 54-company grid/power universe. This is the
concrete answer to "how many fetchers do we build, and what falls to Layer 2?" Source of truth for fetcher scope.*

## Method
For each company: probe live Greenhouse/Lever/Ashby JSON endpoints → if miss, fetch the careers page and
detect the platform signature → if JS-rendered, web-search and read the ATS domain from result URLs →
verify deterministic endpoints live (incl. the Workday `cxs` API). `verification` column: `verified` (hit live,
returned jobs/valid API), `detected` (platform known, endpoint not yet live-confirmed), `layer2` (no clean API).

## Curated expansion log

The platform-distribution table below preserves the original 54-employer grid/power routing pass. Later curated
additions use the same validate-live-then-seed path (D-015) and are recorded here rather than rewriting that
historical baseline.

- **2026-07-14 — SPAN + The Brattle Group:** added to `grid_power_software` as active, verified curated seed
  employers. SPAN's Ashby slug `span` returned 34 postings; Brattle's Greenhouse slug `thebrattlegroup` returned
  21. Both endpoints are slug-derived through the existing generic fetchers (no explicit endpoint or source-code
  change). The seed's fetchable count moves **49 → 51**; production activates them only after Hayden runs the
  post-merge `vja-import-employers` command (D-062).

## Platform distribution (54 employers)

| platform | # | API quality | verification | build tier |
|---|---|---|---|---|
| **Workday** | 15 | clean JSON (`/wday/cxs/{tenant}/{site}/jobs`, POST) | 12 verified, 3 detected | **A** |
| **Greenhouse** | 5 | clean JSON (`boards-api`) | 5 verified | **A** |
| **Lever** | 3 | clean JSON (`api.lever.co`) | 3 verified | **A** |
| **Ashby** | 1 | clean JSON (`posting-api`) | 1 verified | **A** |
| **iCIMS** | 4 | per-company JSON API | detected | **B** |
| **Workable** | 2 | clean JSON (`widget/accounts`) | 2 verified (built, D-049) | **B** |
| **Oracle HCM** | 1 | CE REST API (recruiting cloud) | 1 verified (built, D-051); Honeywell onboarded 2026-07-12 (canonical host via `og:image`, D-078); Con Edison host found (`ejcu`/`CX_1033`) but fails paginate-or-fail 61-of-62 → Layer 2 pending bug look | **B** |
| **SmartRecruiters** | 1 | clean public API | 1 verified (built, D-050) | **B** |
| **Jobvite** | 1 | feed/HTML, messy | detected | **C** |
| **SuccessFactors** | 1 | OData, often auth-gated | detected | **C** |
| **Avature** | 1 | per-client, no std API | detected | **C** |
| **UKG/UltiPro** | 1 | recruiting API | detected | **C** |
| **Eightfold** | 1 | JSON API | detected | **C** |
| **Radancy/TalentBrew** | 3 | server-rendered `/search-jobs/results` HTML | 1 verified (built, D-052); 2 parked (endpoint not yet confirmed) | **C** |
| **Phenom** | 0 grid / 1 aviation (United; SWA/Thales are Workday-under) | `/widgets` JSON API | built + United verified (D-076) | **C** |
| **Paylocity** | 0 seed (4 discovery proposals) | embedded `window.pageData` JSON | built (D-076/D-077); activation pending deploy | **B** |
| **BambooHR** | 0 seed (2 discovery proposals) | clean `/careers/list` JSON | built (D-076); activation pending deploy | **B** |
| **Pinpoint** | 1 grid / 1 aviation proposal | clean `/postings.json` JSON | built + Aurora verified (D-079); Aireon activation pending deploy | **B** |
| **Rippling** | 0 seed (3 discovery proposals) | bare-array board JSON (`api.rippling.com/platform/api/ats/v1/board/{slug}/jobs`) | built + all 3 verified (D-096); activation pending deploy | **B** |
| **Custom** | 13 | no API | layer2 | **D** |

## What this means for the build

- **4 fetchers (Tier A: Workday, Greenhouse, Lever, Ashby) cover 24/54 (44%)** — and they're the cleanest APIs.
  Workday alone is 15 and is **live-verified** (the `cxs` POST returns job counts: AES 111, Vistra 193, S&P 234, Shell 174, etc.).
- **+4 fetchers (Tier B: iCIMS 4, Workable 2, SmartRecruiters 1, Oracle HCM 1 built) → 32/54 (59%)** with 8 fetchers
  total. (Con Edison's Oracle host wasn't found → Layer 2; so 1 of the 2 grid Oracle tenants is fetchable, D-051.)
- **+1 fetcher (Tier C: Radancy/TalentBrew built, D-052) → 33/54 (61%)** with 9 fetchers total — NextEra onboarded
  via the server-rendered `/search-jobs/results` HTML; NRG/National Grid parked until their search base verifies.
- **+1 fetcher (Pinpoint built, D-079) → 34/54 (63%)** — Aurora onboarded through custom-domain config;
  Aireon is an additional aviation proposal that activates through D-077 after deployment.
- **+1 fetcher (Rippling built, D-096)** — 3 discovery proposals (Raptor Maps, Gridsight, Portside = 21 jobs)
  activate through D-077 after deployment. Promoted out of the singleton tail by the 2026-07-26 audit.
- **The next builds are demand-ranked (D-096, re-ranking D-076/D-078)** — the discovery agent is a second demand
  signal alongside the seed universe; see the discovery-demand ledger below. **SWA/Thales Workday config onboards
  are done** (both live-verified 2026-07-11), taking the discovery-expanded production baseline **64 → 66
  fetchable**. Remaining order: **Paylocity + Phenom + BambooHR + Pinpoint + Rippling built** → JazzHR → Jobvite
  → Taleo → **Radancy variants (demoted — see the ledger's probe results)** (defer auth-gated SuccessFactors).
- **Tier D → Layer 2 LLM-read**, exactly as the architecture intends — but it's now the *genuinely-custom* remainder
  (the platform-probe pass D-052 pulled Radancy/Phenom out of Tier D into platform fetchers; the literal LLM-read had
  near-zero reach on those JS portals). No per-company scrapers — the LLM-read fallback handles the rest generically.

**Deterministic ceiling ≈ 38/54 (70%)** reachable with ~8 generic platform fetchers; the remaining ~30% is Layer 2.
This vindicates the "don't write N custom scrapers" call (D-017): the long tail collapses into a handful of platforms.

## Demand ledger (third edition — 2026-07-26 coverage audit, D-096; supersedes the 2026-07-12 second edition)

*Two demand signals feed this: discovery proposals (per-candidate `"provider"` resolutions from the resolver
JSON in `data/discovery_reports/*.md` — NOT raw text mentions) and a live-probe audit of every unfetched prod
row (registry-fetcher validation + careers-page signature detection). Refresh as discovery runs accumulate
(this doubles as the Day-2 "coverage ledger", docs/15).*

**Headline of the third edition: the no-code activation queue is empty.** Five of the six rows the second
edition listed as runbook-activatable are now `active` (ASI, GridBeyond, CivilGrid, Emerald AI, AiDASH);
the sixth, Aloft, was rejected. Every remaining `proposed`/`approved` row needs a **new fetcher** — so the
ranking below is the whole coverage roadmap, not a supplement to a runbook.

| ATS | candidates | status |
|---|---|---|
| **already-supported, validated live 2026-07-12** | 6 → **all resolved**: ASI · GridBeyond · CivilGrid · Emerald AI · AiDASH now `active`; Aloft (greenhouse `versaterm` = parent Versaterm's public-safety board) **rejected → `retired`** (D-096) | **queue closed** |
| **Pinpoint** | **2** (Aireon `aireon.pinpointhq.com` + Aurora Energy Research `careers.auroraer.com` custom domain) | **built (D-079)** — Aurora in curated seed config; Aireon pending post-deploy D-077 `set-ats` + `approve` |
| **Rippling** | **3** (Raptor Maps `raptor-maps-inc` 2 jobs · Gridsight `gridsight` 15 · Portside `portside` 4 = **21**) | **built (D-096)** — promoted from the singleton tail by this audit; bare-JSON board API. Activation pending post-deploy `set-ats` + `approve` on `#103`/`#139`/`#141` |
| **JazzHR** | **3** (Utilidata `utilidata.applytojob.com` 11 · Near Earth `jobs.nearearth.aero` 7 · uAvionix `uavionix.applytojob.com` 3 = **21**) | **D-096 #1 (next)** — HTML-parse build: `/apply/jobs.xml` + `jobs.json` 404 and `/apply/feed` 410, so **no feed exists**. Highest US in-scope density of the tail |
| **Jobvite** | 2 (Uplight `uplight` + Enverus `drillinginfo`) | **D-096 #2** — server-rendered `jobs.jobvite.com/{slug}/search` |
| **Taleo** | 1 tenant / 2 rows (`textron.taleo.net` covers Bell + Textron Aviation) | **D-096 #3** — messy APIs, one build = +2 |
| **Radancy variants** | up to 5, but **demoted from D-078 #2 → D-096 #4** | live re-probe 2026-07-26 killed the projection: **American Airlines 403** · **National Grid 403** · L3Harris `/en/search-jobs/results` returns valid JSON with **`results_len=0`** · NRG aria total is a different format ("Results 1 – 10") · Bombardier renders no `searchresults` table. Five targets, five distinct problems |
| **BambooHR (validated, no DB row)** | Comply365/Vistair (`vistairhr`, **10 postings** live 2026-07-26) | **onboarded (D-096)** — curated seed CSV row, aviation seed-fetchable 15 → 16 |
| re-validate when boards repopulate | Reliable Robotics (lever `reliable`, 0) · Gridmatic (lever `gridmatic`, 0) · Ascend Analytics (greenhouse `ascendanalytics` — API **404**, public board 500) · Skydio (greenhouse evidence, **no working slug**: `skydio`/`skydioinc`/`skydio1` all 404) | fetch OK but 0 postings, or slug unresolved — `set-ats` needs ≥1 |
| Eightfold / UKG / Avature / TriNet / Gusto / Kula / Personio | 1 each, **except Avature → 3** after D-097 | singleton tail — opportunistic; SuccessFactors (JetBlue, Dominion, Indra) stays deferred (auth-gated) |
| Getro / YC Work-at-a-Startup | (portfolio boards) | **not employer ATSs** — parked; revisit as non-employer `sources` (Phase 10) |
| email-only / bot-blocked / EU-only / dead | ~30 rows | retire slate — Hayden-executed runbook (audit chat, 2026-07-12) |
| flagged, not acted on | Aerovy `#111` (ashby `aerovy`, **2 live Seattle software roles**) is `retired` | a human rejection; reversing it is Hayden's call, not an audit action |

**Addendum — what the trading vertical added to this ledger (D-097, 2026-07-26).** The 44 curated rows
resolved **36 fetchable on existing fetchers** (26 Greenhouse, 4 Ashby, 3 Workday, 2 iCIMS, 1 Lever), so
trading needed no new fetcher — the highest same-day yield of any vertical add, because prop shops and quant
funds are overwhelmingly Greenhouse. Its unfetched tail nudges two ranking rows above: **Avature rises to 3
companies** (Koch + Delta + **Two Sigma**, a large engineering org — the strongest case yet for an Avature
build, though Delta's bot-challenge suggests the platform fights server-side fetches), and Eightfold stays
at 1 *company* (Millennium, now holding two rows). Four new `custom`/Layer-2 rows join the tail: **Citadel
Securities**, **D. E. Shaw**, **Bridgewater**, **Trading Technologies** — all four bot-block or JS-render,
which is the same wall D-052's Step-0 probe hit, so they are Layer-2-LLM-read candidates, not fetcher
candidates. Build order is **unchanged**: JazzHR remains #1.

## Recommended build order
1. **Greenhouse, Lever, Ashby** (Weeks 1–2) — 9 companies, trivial, already verified. Proves the loop. ✅
2. **Workday** — 15 companies, biggest single win, `cxs` pattern already validated. ✅
3. **iCIMS** (Tier B, Phase 8 — **done**, D-048) — via the iCIMS **Career Sites (Jibe)**
   `GET {careers_base}/api/jobs` JSON API, **not** the legacy `careers-{tenant}.icims.com` portal (a
   frame-busted SPA with no clean JSON). One generic fetcher, uniform across tenants; rich list payload
   (`apply_url` + full `description` + ISO `update_date`). +6 fetchable (Garmin, Constellation, Exelon,
   SIG, ICE, SITA). Legacy-portal / non-Jibe tenants (Alaska, Joby) → Layer 2.
4. **Workable** (Tier B, Phase 8 — **done**, D-049) — via the embed-widget JSON API
   `GET apply.workable.com/api/v1/widget/accounts/{slug}?details=true` (slug-derived, **single-response**,
   not paginated → the Greenhouse single-request false-closure guard). Rich list (`apply_url`/`description`/
   `published_on` inline). +2 fetchable (Vortexa, Energy Aspects).
5. **SmartRecruiters** (Tier B, Phase 8 — **done**, D-050) — via the public postings API
   `GET api.smartrecruiters.com/v1/companies/{slug}/postings` (slug-derived; limit/offset per page).
   **List-only + paginate-or-fail** on `totalFound` (Workday parity): the list omits the description +
   apply URL, so `apply_url` is constructed (`jobs.smartrecruiters.com/{slug}/{id}`) and the description
   is a lazy `fetch_detail`. +1 fetchable (Vitol).
6. **Oracle HCM / ORC** (Tier B, Phase 8 — **done**, D-051) — via the Candidate-Experience REST API
   `GET {host}/hcmRestApi/.../recruitingCEJobRequisitions?…&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber={CX_n}`
   (explicit per-tenant endpoint; **list-only + paginate-or-fail** on `TotalJobsCount`; `apply_url`
   constructed from `careers_url`; description a lazy `fetch_detail`). +1 fetchable (Southern Company).
   Honeywell (vanity domain proxies the REST API 302→404) + Con Edison (host not exposed) → Layer 2
   until a canonical host + siteNumber is curated (then config-only onboard).
7. **Radancy/TalentBrew** (Tier C, Phase 8 — **done**, D-052) — via the **server-rendered**
   `GET {endpoint}/search-jobs/results` HTML (the JS landing page is empty; one generic bs4 HTML-parse
   fetcher, **list-only + paginate-or-fail** on the table `aria-label` total + lazy `fetch_detail`).
   `external_id` = the `/job/{slug}/{id}` path (Workday parity — the id alone 404s). +1 fetchable
   (NextEra); NRG/National Grid/L3Harris parked `proposed` until their search base verifies.
8. **Workday config onboards: Southwest + Thales** (D-076 — **done**, zero code) — their "Phenom
   portals" are skins over Workday: SWA verified live via the existing `cxs` fetcher
   (`swa:wd1:external`, 47 jobs at onboarding); Thales `thales.wd3`/`Careers` also verified live
   (2,000 global jobs). Seed CSV flipped `custom/layer2 → workday/verified`; production coverage
   baseline 64 → 66 fetchable.
9. **Paylocity** (D-076/D-077 — **built**; discovery demand #1, 4 waiting proposals) — the listing
   page `recruiting.paylocity.com/recruiting/jobs/All/{uuid}/{name}` is **server-rendered with a
   complete embedded `window.pageData` JSON** (`Jobs: [{JobId, JobTitle, LocationName, PublishedDate,
   IsRemote…}]`, no pagination markers) → **single-response false-closure guard** (Workable pattern,
   D-049). `external_id = JobId`; list `Description` is empty → **lazy `fetch_detail`** off
   `/recruiting/jobs/Details/{JobId}/…` (an `extract._DETAIL_RESOLVERS` entry). Endpoint **explicit
   per-tenant** (the uuid/name path — Radancy-style endpoint-only encoding). Discovery host marker
   `recruiting.paylocity.com` already maps. (Note: `/recruiting/v2/api/feed/jobs/{uuid}` exists and
   200s but returns 0 jobs — it is NOT the data path.) Registry + lazy-detail routing are wired;
   D-077 adds validate-before-write `vja-review set-ats`, provider filtering, and parked re-approval.
   Production coverage rises only as waiting proposals are corrected and approved after deploy.
10. **Phenom ✅** (United — the one real Phenom need; Taleo underneath) —
    `POST {base}/widgets` with `ddoKey=refineSearch` is live (United 147 jobs at build): paginate
    `from`/`size` against `totalHits` (**paginate-or-fail**, Workday parity); `external_id = jobId`;
    inline `applyUrl` + `postedDate` + location; full description via `ddoKey=jobDetail` (lazy
    `fetch_detail`, confirmed to accept `jobId` directly). Endpoint is the explicit tenant base with
    required `lang`/`country` query values; no tenant values live in code. United onboarded config-only.
11. **BambooHR ✅** — `GET {slug}.bamboohr.com/careers/list` clean single-response JSON (GridBeyond
    live-verified at build, 2 openings); slug-derived endpoint (`endpoints.py` `_DERIVED_TEMPLATES`);
    `meta.totalCount`-anchored single-response guard; `external_id = id`; trimmed title; structured
    `atsLocation` with legacy/remote fallbacks; constructed public apply URL. Description stays out of
    the list pass and resolves lazily at `/careers/{id}/detail`; only `result.jobOpening` enters extraction,
    never application `formFields`. Registry + lazy-detail routing are wired. GridBeyond (`gridbeyond`) and
    Comply365 (`vistairhr`) remain discovery proposals until the deployed D-077 validate/approve sweep;
    there is no seed change and no direct production mutation in this PR.
12. **Honeywell Oracle config onboard ✅** (D-078 — zero code) — the canonical host leaks via the careers
    page's `og:image`: `ibqbjb.fa.ocs.oraclecloud.com`, siteNumber `CX_1`. Live-validated 1,455 postings
    (global board; US prefilter scopes); constructed apply `/job/{Id}` resolves 200. Seed CSV flipped
    `custom/layer2 → oracle_hcm/verified` 2026-07-12; activates at the next `vja-import-employers` run
    against Neon. (Con Edison's host was found the same day — `ejcu.fa.us6.oraclecloud.com`/`CX_1033` —
    but fails paginate-or-fail deterministically at 61 of 62; investigate before onboarding.)
13. **Pinpoint ✅** (D-078 #1 / D-079) — clean public JSON `GET {tenant}/postings.json`, one rich
    authoritative `data` list with no lazy detail. Canonical hosts derive from the slug; explicit endpoints
    override for custom domains. Aurora Energy Research moved config-only from `custom/layer2` to
    `pinpoint/verified` (+1 curated seed fetchable, 48→49); Aireon (proposal #135) adds the second win after
    deployment through the D-077 `set-ats` + explicit `approve` runbook.
14. **Rippling ✅** (D-096) — slug-derived `GET api.rippling.com/platform/api/ats/v1/board/{slug}/jobs`
    returns a **bare JSON array** that is the complete open set (pagination params are ignored; unknown
    slug 404s), so it takes the single-response guard rather than paginate-or-fail. `external_id = uuid`,
    apply URL supplied, no list date; list-only, with a lazy `…/jobs/{uuid}` detail whose `description`
    is **split into `role` + `company`** (joined `role`-first). **Its list denormalizes one row per
    (job × work location)** — collapsed on `uuid` with locations merged and sorted, guarded so that rows
    disagreeing beyond location still fail closed (the narrowed D-016/D-088 rule). +3 after deployment:
    Raptor Maps, Gridsight, Portside (21 jobs).
15. **JazzHR** (**D-096 #1 — next**) — server-rendered HTML boards (`{slug}.applytojob.com`, custom
    domains like `jobs.nearearth.aero`). Confirmed 2026-07-26 that **no structured feed exists**
    (`/apply/jobs.xml` + `/apply/jobs.json` 404, `/apply/feed` 410), so it is an HTML-parse build per the
    Radancy precedent. **+3 / 21 jobs**: Utilidata (11), Near Earth (7), uAvionix (3) — the highest US
    in-scope density left in the tail.
16. **Jobvite** (D-096 #2) — server-rendered `jobs.jobvite.com/{slug}/search`. +2: Uplight (`uplight`),
    Enverus (`drillinginfo`). Then **Taleo** (D-096 #3): one `textron.taleo.net` tenant covers Bell +
    Textron Aviation (+2). Singleton tail stays opportunistic; SuccessFactors deferred (auth-gated).
17. **Radancy variants** (**demoted to D-096 #4**, was D-078 #2) — extend the D-052 fetcher for the
    probed variants. The 2026-07-26 re-probe removed most of the projected value: **American Airlines
    now 403s** (was "the flagship prize"), **National Grid 403s**, and L3Harris's `/en/search-jobs/results`
    JSON returns `results_len=0` with `hasJobs` — a live board with nothing to map. NRG's aria total is a
    different format ("Results 1 – 10") and Bombardier renders no `searchresults` table. Five targets,
    five distinct problems: sequence it after the clean builds above.
18. **Layer 2 LLM-read** — absorbs the genuinely-custom Tier D + HN/niche sources (where structure truly
    runs out — the platform-probe pass, D-052, showed the literal LLM-read had near-zero reach on the
    platform portals, so it now sits *after* the platform fetchers, not before).

## Endpoint encoding in the seed CSV
- **Greenhouse/Lever/Ashby/Workable/SmartRecruiters/BambooHR/Pinpoint/Rippling:** `ats_slug` = the slug;
  `endpoint` derived from it. (For Rippling the slug is the `ats.rippling.com/{slug}/jobs` token, and the
  custom-domain override does **not** apply — the slug always wins.)
  An explicit endpoint overrides the template for a provider custom domain
  (Aurora Pinpoint).
- **Workday:** `ats_slug` = `tenant:dc:site` (e.g. `aes:wd1:AES_US`); `endpoint` = full `cxs` jobs URL.
  Fetch = `POST {endpoint}` with body `{"limit":20,"offset":0,"appliedFacets":{},"searchText":""}`, paginate by `offset`.
- **Phenom:** explicit tenant base in `endpoint` with required query config, e.g.
  `https://careers.united.com?lang=en_us&country=us`; the fetcher strips the query and posts to `/widgets`.
- **iCIMS/Oracle/Radancy (explicit per-tenant):** `endpoint` holds the per-tenant base (iCIMS Jibe
  `/api/jobs`; Oracle the CE `recruitingCEJobRequisitions` URL incl. `siteNumber`; Radancy the
  search base, e.g. `https://jobs.nexteraenergy.com`, to which the fetcher appends `/search-jobs/results`);
  `careers_url` is the apply base. Radancy carries no `ats_slug` (endpoint-only).
- **Still-detected portals (Jobvite/SuccessFactors/etc.):** `careers_url` holds the portal; `ats_slug`/`endpoint` to be filled when the fetcher is built.
- **layer2:** `careers_url` only; routed to LLM-read.

## Known fixups (status as of the 2026-07-12 audit, D-078)
- **GE Vernova / BP Trading / Fluence** — **resolved** (onboarded at Phase 4.2).
- **Vortexa** — Workable, slug `vortexa` — **confirmed + built** (D-049; 5 open at probe).
- **Honeywell** — **resolved** (step 12 above; onboarded 2026-07-12).
- **Aurora** — **resolved**: Pinpoint custom-domain API, onboarded config-only in step 13 (D-079).
  **Enverus** — confirmed Jobvite (slug `drillinginfo`) — D-078 #4.
- **Castleton (CCI)** — Workday `osv-cci.wd1` re-confirmed 422 → stays Layer 2 (D-032); retire candidate.
- **Con Edison** — Oracle host found (`ejcu.fa.us6.oraclecloud.com`, `CX_1033`) but deterministic
  paginate-or-fail failure at 61 of 62 — bug-shakeout candidate before onboarding; do **not** retire.
- **Jeppesen (Boeing)** — the Boeing Workday board it points at is **already fetched** (seed row `Boeing`);
  recommend CSV `status=retired` as duplicate coverage (the Navitaire/Amadeus case). Hayden's call.
- **Skydio** — Greenhouse confirmed (uuid `gh_jid` links) but the board slug is undiscoverable behind JS;
  parked, revisit.
