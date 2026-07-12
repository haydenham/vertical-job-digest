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
| **Oracle HCM** | 1 | CE REST API (recruiting cloud) | 1 verified (built, D-051); 2 → Layer 2 (host not found) | **B** |
| **SmartRecruiters** | 1 | clean public API | 1 verified (built, D-050) | **B** |
| **Jobvite** | 1 | feed/HTML, messy | detected | **C** |
| **SuccessFactors** | 1 | OData, often auth-gated | detected | **C** |
| **Avature** | 1 | per-client, no std API | detected | **C** |
| **UKG/UltiPro** | 1 | recruiting API | detected | **C** |
| **Eightfold** | 1 | JSON API | detected | **C** |
| **Radancy/TalentBrew** | 3 | server-rendered `/search-jobs/results` HTML | 1 verified (built, D-052); 2 parked (endpoint not yet confirmed) | **C** |
| **Phenom** | 0 grid / 1 aviation (United; SWA/Thales are Workday-under) | `/widgets` JSON API | built + United verified (D-076) | **C** |
| **Paylocity** | 0 seed (4 discovery proposals) | embedded `window.pageData` JSON | built (D-076/D-077); activation pending deploy | **B** |
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
  order: **Paylocity + Phenom built** → BambooHR → JazzHR probe/singletons (defer auth-gated SuccessFactors).
- **Tier D → Layer 2 LLM-read**, exactly as the architecture intends — but it's now the *genuinely-custom* remainder
  (the platform-probe pass D-052 pulled Radancy/Phenom out of Tier D into platform fetchers; the literal LLM-read had
  near-zero reach on those JS portals). No per-company scrapers — the LLM-read fallback handles the rest generically.

**Deterministic ceiling ≈ 38/54 (70%)** reachable with ~8 generic platform fetchers; the remaining ~30% is Layer 2.
This vindicates the "don't write N custom scrapers" call (D-017): the long tail collapses into a handful of platforms.

## Discovery-demand ledger (first edition — 2026-07-10, D-076)

*The Layer-3 discovery agent (D-070/D-074) is now a second demand signal for fetcher priority: every
unsupported ATS on a real proposal is coverage sitting in the review queue, and every newly supported ATS
makes future discovery runs convert into auto-activating employers. Method: per-candidate `"provider"`
resolutions from the resolver JSON in `data/discovery_reports/*.md` — NOT raw text mentions, which the
prompt's own provider list pollutes. Refresh this table as discovery runs accumulate (this doubles as the
Day-2 "coverage ledger" first edition, docs/15).*

| ATS | candidates | status |
|---|---|---|
| **Paylocity** | **4** (Veryon, Trax + 2 grid) | fetcher built; correct + activate via D-077 runbook after deploy |
| already-supported (Lever 3, Ashby 2, Greenhouse 2, Workable 1) | 8 | no work — auto-activate at `vja-review approve` |
| JazzHR | 2 | deterministic host mapping exists (`applytojob.com`); probe `{slug}.applytojob.com` for a feed before building |
| BambooHR | 2 (incl. GridBeyond) | trivial clean JSON (probed) — build after Phenom |
| Kula / Rippling / Gusto / TriNet Hire / Trakstar / Pinpoint | 1 each | singleton tail — opportunistic |
| Getro / YC Work-at-a-Startup | (portfolio boards) | **not employer ATSs** — parked; revisit as non-employer `sources` (Phase 10) |
| careers-page-only / unknown | many | genuinely Layer 2 |

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
11. **BambooHR** — `GET {slug}.bamboohr.com/careers/list` clean single-response JSON (GridBeyond live
    at probe, 2 openings); slug-derived endpoint (`endpoints.py` `_DERIVED_TEMPLATES`);
    single-response guard; `external_id = id`; detail at `/careers/{id}/detail`. Unlocks the parked
    GridBeyond proposal + the startup-heavy discovery tail.
12. **JazzHR probe → Tier C singletons** (Jobvite/SuccessFactors/Avature/UKG/Eightfold +
    Kula/Rippling/Gusto/TriNet/Trakstar/Pinpoint) — probe `{slug}.applytojob.com` for a feed before
    deciding JazzHR; build the rest opportunistically (defer auth-gated SuccessFactors).
13. **Layer 2 LLM-read** — absorbs the genuinely-custom Tier D + HN/niche sources (where structure truly
    runs out — the platform-probe pass, D-052, showed the literal LLM-read had near-zero reach on the
    platform portals, so it now sits *after* the platform fetchers, not before).

## Endpoint encoding in the seed CSV
- **Greenhouse/Lever/Ashby/Workable/SmartRecruiters:** `ats_slug` = the slug; `endpoint` derived from it.
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

## Known fixups (detected, not yet verified)
- **GE Vernova** — Workday tenant `gevernova.wd5`, site path needs correcting (probe returned no total).
- **Castleton (CCI)** — Workday `cci.wd1/ccicareers`, tenant prefix (`osv-`?) needs checking.
- **BP Trading** — Workday tenant `bpinternational.wd3`, site path TBD.
- **Vortexa** — Workable, slug `vortexa` — **confirmed + built** (D-049; 5 open at probe).
- **Fluence / Enverus / Aurora** — marked custom but may be Workday / Greenhouse / Teamtailor respectively; worth a second look before defaulting to Layer 2.
