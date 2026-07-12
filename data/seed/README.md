# Employer seed data

`employers_seed.csv` is the hand-curated starting universe of employers, one row per company.
It is the input to the Layer 1 ATS spine. Nothing vertical-specific lives in code — this file
(plus the vertical config) *is* the vertical.

## Workflow
1. **Hayden curates:** `name` + the priority/context columns (`tier`, `category`, `key_cities`, `role_tilt`).
2. **Claude resolves the ATS:** probes live Greenhouse/Lever/Ashby endpoints to mechanically *verify*
   `ats_type` + `ats_slug` where possible; otherwise fills a best-guess `ats_type` + `careers_url`.
   Every row carries a `verification` value (see below) so confidence is explicit.
3. **Hayden verifies** the `suspect` and `unverified` rows.
4. **Ground truth:** the Layer 1 fetcher loads each endpoint. A 404/empty response means the
   `ats_type`/`ats_slug` is wrong — fix and re-run. Verification is ultimately mechanical, not manual.

## `verification` column — what each value means
| value | meaning | action needed |
|---|---|---|
| `verified` | ATS endpoint hit live and returned jobs / a valid API. | none — trust it |
| `detected` | Platform identified (from careers-page signature or search result URL), but the exact endpoint isn't live-confirmed yet. | confirm endpoint when building that fetcher |
| `layer2` | No clean API; routed to Layer 2 LLM-read-the-page. | none (handled by Layer 2) |

See `docs/07-ats-routing.md` for the full platform distribution and fetcher build priority.

## Columns
| column | who fills | values | notes |
|---|---|---|---|
| `vertical` | Hayden | `aviation_software` \| `grid_power_software` | which vertical this employer belongs to |
| `name` | Hayden | free text | company display name |
| `tier` | Hayden | `Tier 1`…`Tier 5` \| `Bonus` | priority signal; drives crawl ordering / volume estimates |
| `category` | Hayden | free text | e.g. Utility / IPP, Trading / Merchant, Quant Fund, Data SaaS |
| `key_cities` | Hayden | free text | US hubs; useful for the location pre-filter |
| `role_tilt` | Hayden | free text | tech flavor / what kind of roles to expect |
| `ats_type` | Claude | Layer-1 providers include `greenhouse`, `lever`, `ashby`, `workday`, `icims`, `workable`, `oracle_hcm`, `smartrecruiters`, `radancy`, `paylocity`, `phenom`; all values live in `vja.models.AtsType` | which fetcher (or Layer 2) handles this employer |
| `ats_slug` | Claude | free text | the company token in the ATS URL (e.g. Greenhouse `amperon`). For Workday: `tenant:dc:site` (e.g. `aes:wd1:AES_US`). Empty for portal-detected/custom rows. |
| `careers_url` | Claude | URL | the company's job board / careers page ("the job domain"). Required for `workday`/`raw_html`. |
| `endpoint` | derived | URL | constructed for slug-derived ATSs; explicit for Workday, Paylocity, and other per-tenant platforms. |
| `source` | default | `manual` \| `agent_discovered` | how the employer entered the universe. Seed rows are `manual`. |
| `status` | default | `proposed` \| `approved` \| `active` \| `retired` | seed rows default to `active`. |
| `verification` | Claude | `verified` \| `detected` \| `layer2` | confidence in the ATS resolution (see table above). |
| `notes` | optional | free text | anything useful (parent company, ATS quirks, why included). |

For Greenhouse/Lever/Ashby/Workable the fetcher **constructs** the endpoint from `ats_type` + `ats_slug`.
For Workday, Paylocity, and Phenom, `endpoint` holds the per-tenant URL/config. Portal-detected and custom rows carry `careers_url`.

## Current seed status (grid/power vertical, 54 employers)
After the ATS-identification pass (see `docs/07-ats-routing.md`) + the P4.2 Workday + Phase-8
iCIMS/Workable/SmartRecruiters/Oracle/Radancy onboards:
- **33 verified**: Greenhouse (5), Lever (3), Ashby (1), 15 Workday, **2 Workable (Vortexa, Energy
  Aspects — Phase 8)**, **4 iCIMS/Jibe (Constellation, Exelon, SIG, ICE — Phase 8)**,
  **1 SmartRecruiters (Vitol — Phase 8, D-050)**, **1 Oracle ORC (Southern Company — Phase 8, D-051)**,
  **1 Radancy/TalentBrew (NextEra — Phase 8, D-052)**. All 33 are **fetchable today**.
- **8 detected** (platform known, no fetchable endpoint yet): Jobvite (2), SuccessFactors, Avature,
  UKG, Eightfold, **+2 Radancy parked (NRG, National Grid — generic fetcher exists but their
  search base isn't live-confirmed yet; onboard config-only once verified, D-052)**.
- **13 layer2** (no clean API → LLM-read): custom sites, incl. **Con Edison** (Oracle ORC but its
  host isn't exposed — curate canonical host+siteNumber to onboard).

**Deterministic ceiling ≈ 70%** of the universe via ~8 generic platform fetchers; ~30% routes to Layer 2.

## Current seed status (aviation vertical, 36 employers — Phase 7)
The Week-4 "vertical = config" add (D-002/D-004). Curated across all aviation sub-domains (airlines ·
avionics · OEM/manufacturers · GDS/airline-IT · flight-data/analytics · ATM/infrastructure ·
eVTOL/autonomy · travel-tech SaaS), ATS resolved by the same live-probing pass as grid:
- **14 verified** (live endpoint, fetchable today): Greenhouse (2 — OAG, FLYR), Lever (1 — Shield AI),
  Ashby (1 — Beacon AI), Workday (7 — Boeing, Airbus, Wisk Aero, **Sabre, Amadeus — Phase 8**, plus
  **Southwest and Thales — D-076**),
  **iCIMS/Jibe (2 — Garmin, SITA — Phase 8)**, **Phenom (1 — United, D-076)**.
- **2 detected** (platform known, no fetchable endpoint yet): SuccessFactors (JetBlue), **L3Harris
  (Radancy parked — generic fetcher exists but its search base 301-redirects; onboard config-only
  once verified, D-052)**.
- **20 layer2** (no clean API → LLM-read): custom/JS-rendered sites in the flight-data, ATM, and
  remaining OEM/airline tail. Includes
  Collins/RTX (whole-conglomerate Workday board exceeds the ~4000 offset cap → Layer 2, D-046),
  **Alaska** (iCIMS *legacy* portal, no clean Jibe `/api/jobs`), **Joby** (no Jibe API; ATS unconfirmed —
  re-probe), **Honeywell** (Oracle ORC, but its vanity domain proxies the REST API 302→404 — curate
  canonical host+siteNumber to onboard), and **Delta** (Avature: per-job JSON-LD but a 202 bot-challenge
  blocks server-side list fetch). Note: the Greenhouse `archer` board is a **name collision** (a veterinary clinic) — Archer
  Aviation is custom/Layer 2.

The big aerospace Workday boards are whole-company (Collins/RTX 4161, Airbus 2000, Boeing 1168, mostly
non-US/senior); the Stage-A scope gate + Stage-B US/level pre-filter cut this to the early-career US
software slice, same as grid's whole-company boards (GE Vernova etc.).
