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
| **Radancy/Phenom** | 3 | enterprise portal, no clean JSON | layer2 | **D** |
| **Custom** | 14 | no API | layer2 | **D** |

## What this means for the build

- **4 fetchers (Tier A: Workday, Greenhouse, Lever, Ashby) cover 24/54 (44%)** — and they're the cleanest APIs.
  Workday alone is 15 and is **live-verified** (the `cxs` POST returns job counts: AES 111, Vistra 193, S&P 234, Shell 174, etc.).
- **+4 fetchers (Tier B: iCIMS 4, Workable 2, SmartRecruiters 1, Oracle HCM 1 built) → 32/54 (59%)** with 8 fetchers
  total. (Con Edison's Oracle host wasn't found → Layer 2; so 1 of the 2 grid Oracle tenants is fetchable, D-051.)
- **Tier C is 5 singletons** — build opportunistically (SmartRecruiters/Workable-grade easy ones first; defer auth-gated SuccessFactors).
- **Tier D (17/54, 31%) → Layer 2 LLM-read**, exactly as the architecture intends. These are the Radancy/Phenom
  enterprise portals + truly custom sites. No per-company scrapers — the LLM-read fallback handles them generically.

**Deterministic ceiling ≈ 38/54 (70%)** reachable with ~8 generic platform fetchers; the remaining ~30% is Layer 2.
This vindicates the "don't write N custom scrapers" call (D-017): the long tail collapses into a handful of platforms.

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
7. **Tier C singletons** — as time allows.
8. **Layer 2 LLM-read** — absorbs Tier D (and is needed for HN/niche sources anyway).

## Endpoint encoding in the seed CSV
- **Greenhouse/Lever/Ashby/Workable/SmartRecruiters:** `ats_slug` = the slug; `endpoint` derived from it.
- **Workday:** `ats_slug` = `tenant:dc:site` (e.g. `aes:wd1:AES_US`); `endpoint` = full `cxs` jobs URL.
  Fetch = `POST {endpoint}` with body `{"limit":20,"offset":0,"appliedFacets":{},"searchText":""}`, paginate by `offset`.
- **iCIMS/Oracle (explicit per-tenant):** `endpoint` holds the full API URL (iCIMS Jibe `/api/jobs`;
  Oracle the CE `recruitingCEJobRequisitions` URL incl. `siteNumber`); `careers_url` is the apply base.
- **Still-detected portals (Jobvite/SuccessFactors/etc.):** `careers_url` holds the portal; `ats_slug`/`endpoint` to be filled when the fetcher is built.
- **layer2:** `careers_url` only; routed to LLM-read.

## Known fixups (detected, not yet verified)
- **GE Vernova** — Workday tenant `gevernova.wd5`, site path needs correcting (probe returned no total).
- **Castleton (CCI)** — Workday `cci.wd1/ccicareers`, tenant prefix (`osv-`?) needs checking.
- **BP Trading** — Workday tenant `bpinternational.wd3`, site path TBD.
- **Vortexa** — Workable, slug `vortexa` — **confirmed + built** (D-049; 5 open at probe).
- **Fluence / Enverus / Aurora** — marked custom but may be Workday / Greenhouse / Teamtailor respectively; worth a second look before defaulting to Layer 2.
