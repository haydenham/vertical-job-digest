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
| `ats_type` | Claude | `greenhouse` \| `lever` \| `ashby` \| `workday` \| `icims` \| `workable` \| `oracle_hcm` \| `smartrecruiters` \| `jobvite` \| `successfactors` \| `avature` \| `ukg` \| `eightfold` \| `radancy` \| `custom` | which fetcher (or Layer 2) handles this employer |
| `ats_slug` | Claude | free text | the company token in the ATS URL (e.g. Greenhouse `amperon`). For Workday: `tenant:dc:site` (e.g. `aes:wd1:AES_US`). Empty for portal-detected/custom rows. |
| `careers_url` | Claude | URL | the company's job board / careers page ("the job domain"). Required for `workday`/`raw_html`. |
| `endpoint` | derived | URL | constructed in code from `ats_type` + `ats_slug` for GH/Lever/Ashby. Filled by hand for `workday`. |
| `source` | default | `manual` \| `agent_discovered` | how the employer entered the universe. Seed rows are `manual`. |
| `status` | default | `proposed` \| `approved` \| `active` \| `retired` | seed rows default to `active`. |
| `verification` | Claude | `verified` \| `detected` \| `layer2` | confidence in the ATS resolution (see table above). |
| `notes` | optional | free text | anything useful (parent company, ATS quirks, why included). |

For Greenhouse/Lever/Ashby/Workable the fetcher **constructs** the endpoint from `ats_type` + `ats_slug`.
For Workday, `endpoint` holds the full `cxs` jobs URL. Portal-detected (iCIMS/Oracle/etc.) and custom rows carry `careers_url`.

## Current seed status (grid/power vertical, 54 employers)
After the ATS-identification pass (see `docs/07-ats-routing.md`) + the P4.2 Workday + Phase-8 iCIMS/Workable onboards:
- **30 verified**: Greenhouse (5), Lever (3), Ashby (1), 15 Workday, **2 Workable (Vortexa, Energy
  Aspects — Phase 8)**, **4 iCIMS/Jibe (Constellation, Exelon, SIG, ICE — Phase 8)**. All 30 are
  **fetchable today** (Workable now has a generic fetcher, D-049).
- **9 detected** (platform known, endpoint TBD): Oracle HCM (2), SmartRecruiters, Jobvite (2),
  SuccessFactors, Avature, UKG, Eightfold.
- **15 layer2** (no clean API → LLM-read): 3 Radancy/Phenom portals + custom sites.

**Deterministic ceiling ≈ 70%** of the universe via ~8 generic platform fetchers; ~30% routes to Layer 2.

## Current seed status (aviation vertical, 36 employers — Phase 7)
The Week-4 "vertical = config" add (D-002/D-004). Curated across all aviation sub-domains (airlines ·
avionics · OEM/manufacturers · GDS/airline-IT · flight-data/analytics · ATM/infrastructure ·
eVTOL/autonomy · travel-tech SaaS), ATS resolved by the same live-probing pass as grid:
- **11 verified** (live endpoint, fetchable today): Greenhouse (2 — OAG, FLYR), Lever (1 — Shield AI),
  Ashby (1 — Beacon AI), Workday (5 — Boeing, Airbus, Wisk Aero, **Sabre, Amadeus — Phase 8**),
  **iCIMS/Jibe (2 — Garmin, SITA — Phase 8)**.
- **2 detected** (platform known, no generic fetcher yet): SuccessFactors (JetBlue), Oracle HCM (Honeywell).
- **23 layer2** (no clean API → LLM-read): Phenom/Radancy portals (United, Southwest, L3Harris, Thales)
  + custom/JS-rendered sites (the flight-data, ATM, and remaining OEM/airline tail). Includes
  Collins/RTX (whole-conglomerate Workday board exceeds the ~4000 offset cap → Layer 2, D-046),
  **Alaska** (iCIMS *legacy* portal, no clean Jibe `/api/jobs`), **Joby** (no Jibe API; ATS unconfirmed —
  re-probe), and **Delta** (Avature: per-job JSON-LD but a 202 bot-challenge blocks server-side list
  fetch). Note: the Greenhouse `archer` board is a **name collision** (a veterinary clinic) — Archer
  Aviation is custom/Layer 2.

The big aerospace Workday boards are whole-company (Collins/RTX 4161, Airbus 2000, Boeing 1168, mostly
non-US/senior); the Stage-A scope gate + Stage-B US/level pre-filter cut this to the early-career US
software slice, same as grid's whole-company boards (GE Vernova etc.).
