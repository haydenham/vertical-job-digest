# ATS Routing & Fetcher Build Priority

*Output of the ATS-identification pass (2026-06-11) over the 54-company grid/power universe. This is the
concrete answer to "how many fetchers do we build, and what falls to Layer 2?" Source of truth for fetcher scope.*

## Method
For each company: probe live Greenhouse/Lever/Ashby JSON endpoints → if miss, fetch the careers page and
detect the platform signature → if JS-rendered, web-search and read the ATS domain from result URLs →
verify deterministic endpoints live (incl. the Workday `cxs` API). `verification` column: `verified` (hit live,
returned jobs/valid API), `detected` (platform known, endpoint not yet live-confirmed), `layer2` (no clean API).

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
| **Custom** | 14 | no API | layer2 | **D** |

## What this means for the build

- **4 fetchers (Tier A: Workday, Greenhouse, Lever, Ashby) cover 24/54 (44%)** — and they're the cleanest APIs.
  Workday alone is 15 and is **live-verified** (the `cxs` POST returns job counts: AES 111, Vistra 193, S&P 234, Shell 174, etc.).
- **+4 fetchers (Tier B: iCIMS 4, Workable 2, SmartRecruiters 1, Oracle HCM 1 built) → 32/54 (59%)** with 8 fetchers
  total. (Con Edison's Oracle host wasn't found → Layer 2; so 1 of the 2 grid Oracle tenants is fetchable, D-051.)
- **+1 fetcher (Tier C: Radancy/TalentBrew built, D-052) → 33/54 (61%)** with 9 fetchers total — NextEra onboarded
  via the server-rendered `/search-jobs/results` HTML; NRG/National Grid parked until their search base verifies.
- **The next builds are demand-ranked (D-076)** — the discovery agent is now a second demand signal alongside the
  seed universe; see the discovery-demand ledger below. **SWA/Thales Workday config onboards are done** (both
  live-verified 2026-07-11), taking the discovery-expanded production baseline **64 → 66 fetchable**. Remaining
  order: **Paylocity + Phenom + BambooHR built** → JazzHR probe/singletons (defer auth-gated SuccessFactors).
- **Tier D → Layer 2 LLM-read**, exactly as the architecture intends — but it's now the *genuinely-custom* remainder
  (the platform-probe pass D-052 pulled Radancy/Phenom out of Tier D into platform fetchers; the literal LLM-read had
  near-zero reach on those JS portals). No per-company scrapers — the LLM-read fallback handles the rest generically.

**Deterministic ceiling ≈ 38/54 (70%)** reachable with ~8 generic platform fetchers; the remaining ~30% is Layer 2.
This vindicates the "don't write N custom scrapers" call (D-017): the long tail collapses into a handful of platforms.

## Demand ledger (second edition — 2026-07-12 coverage audit, D-078; supersedes the 2026-07-10 first edition)

*Two demand signals feed this: discovery proposals (per-candidate `"provider"` resolutions from the resolver
JSON in `data/discovery_reports/*.md` — NOT raw text mentions) and the 2026-07-12 live-probe audit of every
unfetched prod row (registry-fetcher validation + careers-page signature detection). Refresh as discovery
runs accumulate (this doubles as the Day-2 "coverage ledger", docs/15).*

| ATS | candidates | status |
|---|---|---|
| **already-supported, validated live 2026-07-12** | 6 (ASI ashby · GridBeyond bamboohr · CivilGrid ashby · Emerald AI ashby `emerald-ai` · AiDASH greenhouse `aidashinc` · Aloft greenhouse `versaterm` = parent Versaterm, Hayden's call) | no code — D-077 `set-ats`+`approve` runbook (Hayden runs) |
| **Pinpoint** | **2** (Aireon `aireon.pinpointhq.com` + Aurora Energy Research `careers.auroraer.com` custom domain) | **build next (D-078 #1)** — clean public JSON `GET {tenant}/postings.json`, single-response, BambooHR parity |
| **Radancy variants** | up to **5** (L3Harris: `/en/search-jobs/results` returns JSON · NRG: table rows lack job link, "Results 1 – 10" aria · American Airlines + Bombardier: no `searchresults` table · National Grid: 403) | **D-078 #2** — extend the existing fetcher; L3Harris JSON easiest, AA is the flagship prize |
| **JazzHR** | 2 (Utilidata `utilidata.applytojob.com` + Near Earth `jobs.nearearth.aero`) | **D-078 #3** — server-rendered HTML boards, probed 200 |
| **Jobvite** | 2 (Uplight `uplight` + Enverus `drillinginfo`) | **D-078 #4** — server-rendered `jobs.jobvite.com/{slug}/search` |
| **Taleo** | 1 tenant / 2 rows (`textron.taleo.net` covers Bell + Textron Aviation) | **D-078 #5** — messy APIs, one build = +2 |
| **BambooHR (validated, no DB row)** | Comply365/Vistair (`vistairhr`, 11 postings live) | never persisted — candidate curated seed add |
| re-validate when boards repopulate | Reliable Robotics (lever `reliable`) · Ascend Analytics (greenhouse `ascendanalytics`) · Gridmatic (lever `gridmatic`, board 404s) | fetch OK but 0 postings — `set-ats` needs ≥1 |
| Eightfold / UKG / Avature / TriNet / Rippling / Gusto / Kula / Personio | 1 each | singleton tail — opportunistic; SuccessFactors (JetBlue, Dominion, Indra) stays deferred (auth-gated) |
| Getro / YC Work-at-a-Startup | (portfolio boards) | **not employer ATSs** — parked; revisit as non-employer `sources` (Phase 10) |
| email-only / bot-blocked / EU-only / dead | ~30 rows | retire slate — Hayden-executed runbook (audit chat, 2026-07-12) |

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
13. **Pinpoint** (D-078 #1) — clean public JSON `GET {tenant}/postings.json` (single response; probed live
    on both tenants). Slug-derived host + custom-domain support (Aurora's `careers.auroraer.com` serves the
    same JSON). +2: Aireon (proposed #135) + Aurora Energy Research (seed, currently `custom`).
14. **Radancy variants** (D-078 #2) — extend the D-052 fetcher for the three probed variants: L3Harris's
    `/en/search-jobs/results` **JSON** response (`{filters, results, hasJobs}` — likely easiest), NRG's
    table markup (rows carry no `/job/` link; aria "Results 1 – 10"), and the AA/Bombardier renderer (no
    `searchresults` table). National Grid stays 403-blocked. Up to +5; American Airlines is the flagship.
15. **JazzHR** (D-078 #3) — server-rendered HTML boards (`{slug}.applytojob.com`, custom domains like
    `jobs.nearearth.aero`; both probed 200). HTML-parse per the Radancy precedent. +2: Utilidata, Near Earth.
16. **Jobvite** (D-078 #4) — server-rendered `jobs.jobvite.com/{slug}/search`. +2: Uplight (`uplight`),
    Enverus (`drillinginfo`). Then **Taleo** (D-078 #5): one `textron.taleo.net` tenant covers Bell +
    Textron Aviation (+2). Singleton tail stays opportunistic; SuccessFactors deferred (auth-gated).
17. **Layer 2 LLM-read** — absorbs the genuinely-custom Tier D + HN/niche sources (where structure truly
    runs out — the platform-probe pass, D-052, showed the literal LLM-read had near-zero reach on the
    platform portals, so it now sits *after* the platform fetchers, not before).

## Endpoint encoding in the seed CSV
- **Greenhouse/Lever/Ashby/Workable/SmartRecruiters/BambooHR:** `ats_slug` = the slug; `endpoint` derived from it.
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
- **Aurora** — not Teamtailor: **Pinpoint** (`careers.auroraer.com/postings.json` live) — activates with the
  D-078 #1 build. **Enverus** — confirmed Jobvite (slug `drillinginfo`) — D-078 #4.
- **Castleton (CCI)** — Workday `osv-cci.wd1` re-confirmed 422 → stays Layer 2 (D-032); retire candidate.
- **Con Edison** — Oracle host found (`ejcu.fa.us6.oraclecloud.com`, `CX_1033`) but deterministic
  paginate-or-fail failure at 61 of 62 — bug-shakeout candidate before onboarding; do **not** retire.
- **Jeppesen (Boeing)** — the Boeing Workday board it points at is **already fetched** (seed row `Boeing`);
  recommend CSV `status=retired` as duplicate coverage (the Navitaire/Amadeus case). Hayden's call.
- **Skydio** — Greenhouse confirmed (uuid `gh_jid` links) but the board slug is undiscoverable behind JS;
  parked, revisit.
